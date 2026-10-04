"""What each endpoint does. The router only parses requests and calls these functions."""
import json
from collections import Counter
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Optional

from backend.shared.db import get_supabase
from backend.shared.errors import AppError, NotFound
from backend.shared.llm import get_llm
from backend.shared.settings import get_settings

from .copilot import Deps, run_copilot
from .knowledge import KnowledgeBase
from .order_facts import build_facts
from .repository import DemoRepository, SupabaseRepository
from .schemas import (AnalyzeTextRequest, CopilotResult, CXMetrics, DecisionRequest, DecisionResponse,
                      InboxItem, InboxPage, TicketDetail, TicketSummary)

DECIDED_STATUS = {"APPROVED": "RESOLVED", "EDITED": "RESOLVED", "REJECTED": "ESCALATED", "ESCALATED": "ESCALATED"}


@lru_cache
def get_deps() -> Deps:
    s = get_settings()
    repo = SupabaseRepository(get_supabase(), s.knowledge_bucket) if s.cx_mode == "supabase" else DemoRepository()
    return Deps(repo=repo, llm=get_llm(), kb=KnowledgeBase(repo), settings=s)


def _output(row: Optional[dict]) -> dict:
    out = (row or {}).get("output") or {}
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except ValueError:
            out = {}
    return out


def _intent(out: dict) -> Optional[str]:
    return (out.get("classification") or {}).get("intent") or out.get("intent")


def list_tickets(deps: Deps, status: Optional[str], channel: Optional[str], intent: Optional[str],
                 limit: int, offset: int) -> list[TicketSummary]:
    tickets = deps.repo.list_tickets(status, channel, limit, offset)
    latest = deps.repo.latest_interactions([t.ticket_id for t in tickets])
    rows = []
    for t in tickets:
        out = _output(latest.get(t.ticket_id))
        rows.append(TicketSummary(ticket_id=t.ticket_id, ticket_number=t.ticket_number, customer_name=t.customer_name,
                                  channel=t.channel, message=t.message, status=t.status, created_at=t.created_at,
                                  last_intent=_intent(out), last_result=out.get("status")))
    return [r for r in rows if not intent or r.last_intent == intent]


def _ticket(deps: Deps, ref: str):
    ticket = deps.repo.get_ticket(ref)
    if not ticket:
        raise NotFound("TICKET_NOT_FOUND", f"No ticket {ref}")
    return ticket


def ticket_detail(deps: Deps, ref: str) -> TicketDetail:
    ticket = _ticket(deps, ref)
    order = deps.repo.get_order(ticket.order_id) if ticket.order_id else None
    facts = build_facts(order, deps.today(), deps.settings.return_window_days) if order else None
    last = deps.repo.latest_interactions([ticket.ticket_id]).get(ticket.ticket_id)
    last_result = {**_output(last), "interaction_id": last["interaction_id"],
                   "human_action": last.get("human_action")} if last else None
    ticket.status = _shown_status(ticket.status, (last_result or {}).get("status"), (last_result or {}).get("human_action"))
    others = [t for t in deps.repo.customer_tickets(ticket.customer_id, 6) if t.ticket_id != ticket.ticket_id][:5]
    runs = deps.repo.latest_interactions([t.ticket_id for t in others]) if others else {}
    history = []
    for t in others:
        run = runs.get(t.ticket_id) or {}
        history.append(TicketSummary(
            ticket_id=t.ticket_id, ticket_number=t.ticket_number, customer_name=t.customer_name, channel=t.channel,
            message=t.message, created_at=t.created_at,
            status=_shown_status(t.status, _output(run).get("status"), run.get("human_action"))))
    return TicketDetail(ticket=ticket, order=order, facts=facts, last_result=last_result, history=history)


# ---------- Inbox: search, views and priority over every ticket ----------
ACTIVE = {"OPEN", "IN_PROGRESS", "DRAFTED"}
HAS_DRAFT = {"DRAFTED", "NEEDS_INFO"}


def _shown_status(status: str, result: Optional[str], human_action: Optional[str]) -> str:
    """The database marks some tickets IN_PROGRESS (shown to us as DRAFTED) without any Copilot run.
    Only call it a draft when Copilot actually wrote one that nobody has decided on yet."""
    if status == "DRAFTED" and not (result in HAS_DRAFT and not human_action):
        return "IN_PROGRESS"
    return status
NOT_IN_TRANSIT = {"DELIVERED", "CANCELLED", "RTO", "RETURNED"}
URGENT_DAYS_LATE = 7


def _days_late(row: dict, today: date) -> Optional[int]:
    exp = row.get("expected_delivery")
    if not exp or (row.get("order_status") or "").upper() in NOT_IN_TRANSIT:
        return None
    late = (today - (date.fromisoformat(exp[:10]) if isinstance(exp, str) else exp)).days
    return late if late > 0 else None


def _view(item: InboxItem) -> str:
    if item.needs_person:
        return "needs_person"
    return {"DRAFTED": "drafted", "RESOLVED": "resolved", "ESCALATED": "escalated"}.get(item.status, "open")


def _priority(item: InboxItem):
    """Higher first: unresolved, then very late orders and repeat askers, then the oldest."""
    score = min(item.days_late or 0, 30) + 15 * (item.repeat_count - 1)
    return (item.status not in ACTIVE, -score, item.ticket_number)


def inbox(deps: Deps, view: str, intent: Optional[str], q: Optional[str], sort: str,
          limit: int, offset: int) -> InboxPage:
    index = deps.repo.ticket_index()
    results = deps.repo.latest_results()
    today = deps.today()
    repeats = Counter(r["order_id"] for r in index if r.get("order_id") and r["status"] in ACTIVE)

    items = []
    for r in index:
        res = results.get(r["ticket_id"]) or {}
        status = _shown_status(r["status"], res.get("result"), res.get("human_action"))
        active = status in ACTIVE
        late = _days_late(r, today)
        repeat = repeats.get(r.get("order_id"), 1) if active else 1
        items.append(InboxItem(
            ticket_id=r["ticket_id"], ticket_number=r["ticket_number"], customer_name=r["customer_name"],
            channel=r.get("channel"), message=r["message"], status=status, created_at=r.get("created_at"),
            last_intent=res.get("intent"), last_result=res.get("result"), order_number=r.get("order_number"),
            days_late=late, repeat_count=repeat,
            needs_person=status in ("OPEN", "IN_PROGRESS") and res.get("result") == "NEEDS_HUMAN" and not res.get("human_action"),
            urgent=active and ((late or 0) >= URGENT_DAYS_LATE or repeat > 1),
        ))

    counts = Counter(_view(i) for i in items)
    counts["all"] = len(items)
    needle = (q or "").strip().lower()
    hits = [i for i in items
            if (view == "all" or _view(i) == view)
            and (not intent or i.last_intent == intent)
            and (not needle or any(needle in (v or "").lower()
                                   for v in (i.ticket_number, i.customer_name, i.message, i.order_number)))]
    if sort == "priority":
        hits.sort(key=_priority)
    else:
        hits.sort(key=lambda i: i.ticket_number, reverse=sort == "newest")
    return InboxPage(total=len(hits), counts=dict(counts), items=hits[offset:offset + limit])


def analyze_ticket(deps: Deps, ref: str) -> CopilotResult:
    ticket = _ticket(deps, ref)
    if ticket.status in ("RESOLVED", "ESCALATED"):
        raise AppError("TICKET_CLOSED", f"Ticket {ticket.ticket_number} is already {ticket.status.lower()}", 409)
    result = run_copilot(deps, message=ticket.message, customer_name=ticket.customer_name,
                         customer_id=ticket.customer_id, linked_order_id=ticket.order_id, ticket_id=ticket.ticket_id)
    if result.status in ("DRAFTED", "NEEDS_INFO"):
        deps.repo.update_ticket_status(ticket.ticket_id, "DRAFTED")
    return result


def analyze_text(deps: Deps, req: AnalyzeTextRequest) -> CopilotResult:
    message = f"{req.message}\n(Order number: {req.order_number})" if req.order_number else req.message
    return run_copilot(deps, message=message, customer_id=req.customer_id)


def record_decision(deps: Deps, ref: str, req: DecisionRequest) -> DecisionResponse:
    ticket = _ticket(deps, ref)
    row = deps.repo.get_interaction(req.interaction_id)
    if not row:
        raise NotFound("INTERACTION_NOT_FOUND", f"No Copilot result {req.interaction_id}")
    if row.get("input_reference_id") != ticket.ticket_id:
        raise AppError("INTERACTION_MISMATCH", "That Copilot result belongs to a different ticket")
    if row.get("human_action"):
        raise AppError("ALREADY_DECIDED", f"This result was already {row['human_action'].lower()}", 409)

    out = _output(row)
    if req.action == "EDITED" and not (req.final_reply or "").strip():
        raise AppError("FINAL_REPLY_REQUIRED", "An edited decision needs the final reply text")
    if req.action == "APPROVED" and not out.get("draft"):
        raise AppError("NO_DRAFT", "There is no draft to approve. Edit a reply or escalate instead")
    final = req.final_reply if req.action == "EDITED" else out.get("draft") if req.action == "APPROVED" else None

    out.update(final_reply=final, decided_at=datetime.now(timezone.utc).isoformat())
    deps.repo.update_interaction(req.interaction_id, {"human_action": req.action, "output": out})
    new_status = DECIDED_STATUS[req.action]
    deps.repo.update_ticket_status(ticket.ticket_id, new_status)
    return DecisionResponse(ticket_id=ticket.ticket_id, ticket_status=new_status, human_action=req.action)


def order_lookup(deps: Deps, order_number: str) -> dict:
    order = deps.repo.find_order(order_number.upper())
    if not order:
        raise NotFound("ORDER_NOT_FOUND", f"No order {order_number}")
    return {"order": order, "facts": build_facts(order, deps.today(), deps.settings.return_window_days)}


def metrics(deps: Deps) -> CXMetrics:
    rows = deps.repo.list_interactions()
    outs = [_output(r) for r in rows]
    actions = Counter(r["human_action"] for r in rows if r.get("human_action"))
    decided = sum(actions[a] for a in ("APPROVED", "EDITED", "REJECTED"))
    latencies = [r["processing_time_ms"] for r in rows if r.get("processing_time_ms") is not None]
    costs = [o["cost_usd"] for o in outs if isinstance(o.get("cost_usd"), (int, float))]
    return CXMetrics(
        tickets_by_status=deps.repo.count_tickets_by_status(),
        analysed=len(rows),
        by_intent=dict(Counter(i for i in map(_intent, outs) if i)),
        by_result=dict(Counter(o["status"] for o in outs if o.get("status"))),
        human_actions=dict(actions),
        acceptance_rate=round(actions["APPROVED"] / decided, 4) if decided else None,
        fallback_runs=sum(1 for o in outs if o.get("fallback_mode")),
        avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else None,
        avg_cost_usd=round(sum(costs) / len(costs), 6) if costs else None,
        total_cost_usd=round(sum(costs), 6),
    )

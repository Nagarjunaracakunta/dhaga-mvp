"""Repeated questions: draft many open tickets at once, then let an agent approve them group by group.

Copilot still runs every ticket through the full workflow (rules, facts, checks). Only drafts that passed the
checks, came from the model (not fallback templates) and have intent confidence >= bulk_min_confidence join the
queue. Nothing is sent to a customer here: approving is still a person's decision.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from backend.shared.errors import AppError

from . import service
from .copilot import Deps
from .schemas import (BulkApproveRequest, BulkApproveResponse, BulkApproveResult, BulkDraftResponse, BulkGroup,
                      BulkItem, BulkQueue, DecisionRequest)

INTENT_ORDER = ["WISMO", "CANCEL_ORDER", "RETURN_REFUND", "COD_PAYMENT", "DELIVERED_NOT_RECEIVED",
                "DAMAGED_OR_WRONG_ITEM", "OTHER"]
SCAN = 200  # tickets read per page when building the queue


def qualifies(out: dict, human_action, min_confidence: float) -> bool:
    c = out.get("classification") or {}
    return (out.get("status") == "DRAFTED" and not human_action and not out.get("fallback_mode")
            and bool(out.get("draft")) and (out.get("check") or {}).get("passed") is True
            and (c.get("confidence") or 0) >= min_confidence)


def _not_yet_analysed(deps: Deps, limit: int):
    """Oldest open tickets Copilot has not run on. Tickets it handed to a person stay OPEN, so skip those."""
    picked, offset = [], 0
    while len(picked) < limit:
        page = deps.repo.list_tickets("OPEN", None, SCAN, offset)
        if not page:
            break
        seen = deps.repo.latest_interactions([t.ticket_id for t in page])
        picked += [t for t in page if t.ticket_id not in seen]
        offset += SCAN
    return picked[:limit]


def draft_open_tickets(deps: Deps, limit: int) -> BulkDraftResponse:
    cap = deps.settings.bulk_max_tickets
    if limit > cap:
        raise AppError("BULK_LIMIT", f"At most {cap} tickets per run (each draft costs about $0.01)")
    tickets = _not_yet_analysed(deps, limit)

    def one(t):
        try:
            return service.analyze_ticket(deps, t.ticket_number)
        except Exception:  # one bad ticket must not stop the batch; it stays OPEN
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, tickets))

    ok = [r for r in results if r]
    ready = sum(1 for r in ok if qualifies(r.model_dump(mode="json"), None, deps.settings.bulk_min_confidence))
    drafted = sum(1 for r in ok if r.status == "DRAFTED")
    return BulkDraftResponse(analysed=len(tickets), ready=ready, needs_person=sum(1 for r in ok if r.status != "DRAFTED"),
                             below_threshold=drafted - ready, failed=len(results) - len(ok),
                             cost_usd=round(sum(r.cost_usd for r in ok), 6))


def queue(deps: Deps) -> BulkQueue:
    s = deps.settings
    tickets, offset = [], 0
    while True:
        page = deps.repo.list_tickets("DRAFTED", None, SCAN, offset)
        tickets += page
        if len(page) < SCAN:
            break
        offset += SCAN
    latest = deps.repo.latest_interactions([t.ticket_id for t in tickets]) if tickets else {}

    items = defaultdict(list)
    for t in tickets:
        row = latest.get(t.ticket_id)
        out = service._output(row)
        if not row or not qualifies(out, row.get("human_action"), s.bulk_min_confidence):
            continue
        facts = out.get("facts") or {}
        items[out["classification"]["intent"]].append(BulkItem(
            ticket_number=t.ticket_number, customer_name=t.customer_name, message=t.message,
            interaction_id=row["interaction_id"], confidence=out["classification"]["confidence"], draft=out["draft"],
            order_number=facts.get("order_number"), order_status=facts.get("status")))

    # The same order asked about in several open tickets is a repeat: show it so the agent can reply once.
    per_order = Counter(i.order_number for group in items.values() for i in group if i.order_number)
    for group in items.values():
        for i in group:
            i.repeat_count = per_order.get(i.order_number, 1)

    groups = [BulkGroup(intent=k, count=len(v), items=v) for k, v in items.items()]
    groups.sort(key=lambda g: (-g.count, INTENT_ORDER.index(g.intent) if g.intent in INTENT_ORDER else 99))
    return BulkQueue(min_confidence=s.bulk_min_confidence, max_per_run=s.bulk_max_tickets,
                     open_tickets=deps.repo.count_tickets_by_status().get("OPEN", 0), groups=groups)


def approve(deps: Deps, req: BulkApproveRequest) -> BulkApproveResponse:
    results = []
    for item in req.items:
        try:
            row = deps.repo.get_interaction(item.interaction_id)
            if not row or not qualifies(service._output(row), row.get("human_action"), deps.settings.bulk_min_confidence):
                raise AppError("NOT_IN_QUEUE", "This draft is no longer in the bulk queue; open the ticket instead")
            service.record_decision(deps, item.ticket_ref, DecisionRequest(interaction_id=item.interaction_id,
                                                                          action="APPROVED"))
            results.append(BulkApproveResult(ticket_ref=item.ticket_ref, ok=True))
        except AppError as e:
            results.append(BulkApproveResult(ticket_ref=item.ticket_ref, ok=False, error=e.message))
    return BulkApproveResponse(approved=sum(r.ok for r in results), results=results)

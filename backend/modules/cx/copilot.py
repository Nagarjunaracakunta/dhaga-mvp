"""The CX Copilot workflow: classify -> find order -> facts -> rules -> policy -> draft -> check -> log.

Patterns used: routing (intent decides facts + policy) and evaluator-optimizer (failed check -> one redraft).
"""
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from backend.shared.llm import LLM, LLMOutputError, LLMUnavailable
from backend.shared.settings import Settings

from . import checker, classifier, drafter, fallback, rules
from .knowledge import KnowledgeBase
from .order_facts import build_facts
from .repository import WORKFLOW, CXRepository
from .schemas import CopilotResult, DraftCheck, OrderRecord, TicketClassification

PROMPT_VERSIONS = f"{classifier.PROMPT_VERSION}+{drafter.PROMPT_VERSION}+{checker.PROMPT_VERSION}"


@dataclass
class Deps:
    repo: CXRepository
    llm: LLM
    kb: KnowledgeBase
    settings: Settings

    def today(self) -> date:
        return self.settings.cx_today or self.repo.today_default or date.today()


@dataclass
class _Run:
    """Collects cost, timing and notes across the steps of one run."""
    started: float = field(default_factory=time.perf_counter)
    cost: float = 0.0
    models: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fallback: bool = False

    def add(self, result):
        self.cost += result.cost_usd
        if result.model not in self.models:
            self.models.append(result.model)
        return result.parsed

    def went_offline(self, reason: str):
        if not self.fallback:
            self.notes.append(f"Fallback mode: {reason}")
        self.fallback = True


def _classify(deps: Deps, run: _Run, message: str) -> TicketClassification:
    if not run.fallback:
        try:
            return run.add(classifier.classify(deps.llm, message, deps.settings))
        except LLMUnavailable as e:
            run.went_offline(str(e))
        except LLMOutputError as e:
            run.notes.append(f"Classifier output unusable: {e}")
            return TicketClassification(intent="OTHER", confidence=0.0, order_number=None, language="other")
    return fallback.classify_by_keywords(message)


def _find_order(deps: Deps, run: _Run, c: TicketClassification, customer_id: Optional[str],
                linked_order_id: Optional[str]) -> tuple[Optional[OrderRecord], bool]:
    """Customer's own number first, then the ticket's linked order, then their latest order."""
    if c.order_number:
        order = deps.repo.find_order(c.order_number)
        if order and customer_id and order.customer_id != customer_id:
            return None, True
        if order:
            return order, False
        run.notes.append(f"Order {c.order_number} from the message was not found.")
    if linked_order_id:
        order = deps.repo.get_order(linked_order_id)
        if order:
            return order, False
    if customer_id:
        return deps.repo.latest_order(customer_id), False
    return None, False


def run_copilot(deps: Deps, *, message: str, customer_name: Optional[str] = None, customer_id: Optional[str] = None,
                linked_order_id: Optional[str] = None, ticket_id: Optional[str] = None) -> CopilotResult:
    s, run = deps.settings, _Run()
    first_name = (customer_name or "").split()[0] if customer_name else "there"

    # 1-4: classify, find the order, compute facts, apply rules
    c = _classify(deps, run, message)
    order, mismatch = _find_order(deps, run, c, customer_id, linked_order_id)
    facts = build_facts(order, deps.today(), s.return_window_days) if order else None
    decision = rules.decide(c, facts, mismatch, s.min_intent_confidence, s.delay_priority_days)

    policy = deps.kb.for_intent(c.intent)
    status, draft, check, human_reason, attempts = "NEEDS_HUMAN", None, None, decision.reason, 0

    if decision.action == "NEEDS_INFO":
        status, draft = "NEEDS_INFO", fallback.needs_info_reply(first_name)

    elif decision.action == "DRAFT":
        issues: list[str] = []
        for attempts in range(1, s.max_draft_attempts + 1):
            # 5: draft (model, or template when offline)
            if not run.fallback:
                try:
                    draft = run.add(drafter.draft(deps.llm, s, message=message, first_name=first_name, classification=c,
                                                  facts=facts, policy=policy, priority_note=decision.priority_note,
                                                  previous_issues=issues)).reply
                except LLMUnavailable as e:
                    run.went_offline(str(e))
                except LLMOutputError as e:
                    human_reason, draft, check = f"AI draft could not be used: {e}", None, None
                    break
            if run.fallback:
                draft = fallback.template_reply(c.intent, facts, first_name)

            # 6: check (code always; model when online)
            issues = checker.code_check(draft, facts)
            if not issues and not run.fallback:
                try:
                    verdict = run.add(checker.model_check(deps.llm, s, message=message, reply=draft, facts=facts, policy=policy))
                    issues = [] if verdict.passed else (verdict.issues or ["Reviewer model rejected the draft."])
                except LLMUnavailable as e:
                    run.notes.append(f"Model check skipped: {e}")
                except LLMOutputError as e:
                    run.notes.append(f"Model check unusable: {e}")
            check = DraftCheck(passed=not issues, issues=issues)
            if check.passed or run.fallback:
                break

        if check and check.passed:
            status, human_reason = "DRAFTED", None
        elif check:
            human_reason = "The draft failed the automatic check twice. Review it carefully or reply manually."

    latency_ms = int((time.perf_counter() - run.started) * 1000)
    result = CopilotResult(
        ticket_id=ticket_id, status=status, classification=c, facts=facts,
        policy_used=policy.name if policy and draft and status != "NEEDS_INFO" and not run.fallback else None,
        draft=draft, check=check, human_reason=human_reason, escalation_tier=decision.escalation_tier,
        priority_note=decision.priority_note, attempts=attempts, fallback_mode=run.fallback, notes=run.notes,
        interaction_id=None, cost_usd=round(run.cost, 6), latency_ms=latency_ms,
    )

    # 7: log every run
    evaluation = "PASSED" if status == "DRAFTED" else ("FAILED" if check and not check.passed else "REVIEW_REQUIRED")
    result.interaction_id = deps.repo.insert_interaction({
        "workflow": WORKFLOW,
        "input_reference_type": "support_ticket" if ticket_id else None,
        "input_reference_id": ticket_id,
        "model_name": ", ".join(run.models) or "fallback-rules",
        "prompt_version": PROMPT_VERSIONS,
        "input_summary": message[:200],
        "output": result.model_dump(mode="json", exclude={"interaction_id"}),
        "confidence": round(c.confidence, 4),
        "evaluation_status": evaluation,
        "human_action": None,
        "processing_time_ms": latency_ms,
    })
    return result

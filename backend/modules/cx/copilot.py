"""The CX Copilot workflow, built as a LangChain RunnableSequence:
classify -> find order -> facts -> rules -> policy -> (person | ask for order | draft + check) -> log.

Patterns used: routing (RunnableBranch on the rules' decision) and evaluator-optimizer (failed check -> one redraft).
"""
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough

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


# ---------------------------------------------------------------- the workflow as a LangChain RunnableSequence
# A state dict flows through named steps; each RunnablePassthrough.assign adds one key. Routing is a RunnableBranch.
# The draft -> check -> redraft-once loop (evaluator-optimizer) lives inside one step, because a sequence only
# flows forward.

def _step_classify(st):
    return _classify(st["deps"], st["run"], st["message"])


def _step_find_order(st):
    order, mismatch = _find_order(st["deps"], st["run"], st["classification"], st["customer_id"], st["linked_order_id"])
    return {"order": order, "mismatch": mismatch}


def _step_facts(st):
    order, s = st["order_info"]["order"], st["deps"].settings
    return build_facts(order, st["deps"].today(), s.return_window_days) if order else None


def _step_rules(st):
    s = st["deps"].settings
    return rules.decide(st["classification"], st["facts"], st["order_info"]["mismatch"],
                        s.min_intent_confidence, s.delay_priority_days)


def _step_policy(st):
    return st["deps"].kb.for_intent(st["classification"].intent)


def _outcome(status, draft=None, check=None, human_reason=None, attempts=0):
    return {"status": status, "draft": draft, "check": check, "human_reason": human_reason, "attempts": attempts}


def _step_hand_to_person(st):
    return _outcome("NEEDS_HUMAN", human_reason=st["decision"].reason)


def _step_ask_for_order_number(st):
    return _outcome("NEEDS_INFO", draft=fallback.needs_info_reply(st["first_name"]), human_reason=st["decision"].reason)


def _step_draft_and_check(st):
    """Evaluator-optimizer: draft, check with code then Haiku, redraft once with the issues listed."""
    deps, run, s = st["deps"], st["run"], st["deps"].settings
    c, facts, policy, decision = st["classification"], st["facts"], st["policy"], st["decision"]
    draft, check, human_reason, attempts, issues = None, None, decision.reason, 0, []
    for attempts in range(1, s.max_draft_attempts + 1):
        if not run.fallback:
            try:
                draft = run.add(drafter.draft(deps.llm, s, message=st["message"], first_name=st["first_name"],
                                              classification=c, facts=facts, policy=policy,
                                              priority_note=decision.priority_note, previous_issues=issues)).reply
            except LLMUnavailable as e:
                run.went_offline(str(e))
            except LLMOutputError as e:
                return _outcome("NEEDS_HUMAN", human_reason=f"AI draft could not be used: {e}", attempts=attempts)
        if run.fallback:
            draft = fallback.template_reply(c.intent, facts, st["first_name"])

        issues = checker.code_check(draft, facts)
        if not issues and not run.fallback:
            try:
                verdict = run.add(checker.model_check(deps.llm, s, message=st["message"], reply=draft, facts=facts,
                                                      policy=policy, today=deps.today()))
                issues = [] if verdict.passed else (verdict.issues or ["Reviewer model rejected the draft."])
            except LLMUnavailable as e:
                run.notes.append(f"Model check skipped: {e}")
            except LLMOutputError as e:
                run.notes.append(f"Model check unusable: {e}")
        check = DraftCheck(passed=not issues, issues=issues)
        if check.passed or run.fallback:
            break

    if check and check.passed:
        return _outcome("DRAFTED", draft=draft, check=check, attempts=attempts)
    return _outcome("NEEDS_HUMAN", draft=draft, check=check, attempts=attempts,
                    human_reason="The draft failed the automatic check twice. Review it carefully or reply manually.")


def _step_build_and_log(st):
    deps, run, o, c = st["deps"], st["run"], st["outcome"], st["classification"]
    policy, decision = st["policy"], st["decision"]
    latency_ms = int((time.perf_counter() - run.started) * 1000)
    result = CopilotResult(
        ticket_id=st["ticket_id"], status=o["status"], classification=c, facts=st["facts"],
        policy_used=policy.name if policy and o["draft"] and o["status"] != "NEEDS_INFO" and not run.fallback else None,
        draft=o["draft"], check=o["check"], human_reason=o["human_reason"], escalation_tier=decision.escalation_tier,
        priority_note=decision.priority_note, attempts=o["attempts"], fallback_mode=run.fallback, notes=run.notes,
        interaction_id=None, cost_usd=round(run.cost, 6), latency_ms=latency_ms,
    )
    check = o["check"]
    evaluation = ("PASSED" if o["status"] == "DRAFTED"
                  else "FAILED" if check and not check.passed else "REVIEW_REQUIRED")
    result.interaction_id = deps.repo.insert_interaction({
        "workflow": WORKFLOW,
        "input_reference_type": "support_ticket" if st["ticket_id"] else None,
        "input_reference_id": st["ticket_id"],
        "model_name": ", ".join(run.models) or "fallback-rules",
        "prompt_version": PROMPT_VERSIONS,
        "input_summary": st["message"][:200],
        "output": result.model_dump(mode="json", exclude={"interaction_id"}),
        "confidence": round(c.confidence, 4),
        "evaluation_status": evaluation,
        "human_action": None,
        "processing_time_ms": latency_ms,
    })
    return result


def _action_is(action):
    return lambda st: st["decision"].action == action


COPILOT_CHAIN = (
    RunnablePassthrough.assign(classification=RunnableLambda(_step_classify, name="classify_intent"))      # AI
    | RunnablePassthrough.assign(order_info=RunnableLambda(_step_find_order, name="find_order"))           # code
    | RunnablePassthrough.assign(facts=RunnableLambda(_step_facts, name="order_facts"))                    # code
    | RunnablePassthrough.assign(decision=RunnableLambda(_step_rules, name="apply_rules"))                 # code
    | RunnablePassthrough.assign(policy=RunnableLambda(_step_policy, name="pick_policy"))                  # code
    | RunnablePassthrough.assign(outcome=RunnableBranch(                                                   # routing
        (_action_is("NEEDS_HUMAN"), RunnableLambda(_step_hand_to_person, name="hand_to_person")),
        (_action_is("NEEDS_INFO"), RunnableLambda(_step_ask_for_order_number, name="ask_for_order_number")),
        RunnableLambda(_step_draft_and_check, name="draft_and_check"),                                     # AI + code
    ))
    | RunnableLambda(_step_build_and_log, name="build_and_log_result")                                     # code
)
STEP_NAMES = ["classify_intent", "find_order", "order_facts", "apply_rules", "pick_policy",
              "hand_to_person | ask_for_order_number | draft_and_check", "build_and_log_result"]


def run_copilot(deps: Deps, *, message: str, customer_name: Optional[str] = None, customer_id: Optional[str] = None,
                linked_order_id: Optional[str] = None, ticket_id: Optional[str] = None) -> CopilotResult:
    """Run one ticket through COPILOT_CHAIN."""
    return COPILOT_CHAIN.invoke({
        "deps": deps, "run": _Run(), "message": message, "customer_id": customer_id,
        "linked_order_id": linked_order_id, "ticket_id": ticket_id,
        "first_name": (customer_name or "").split()[0] if customer_name else "there",
    })

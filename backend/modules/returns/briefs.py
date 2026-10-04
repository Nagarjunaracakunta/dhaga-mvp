"""Evaluator-optimizer: an LLM writes an investigation brief per flagged insight; a second
model fact-checks it against the numbers; it loops until it passes or is flagged for a human.

Writer = Sonnet 5.5 (temp 0.3). Judge = Haiku 4.5 (temp 0). All arithmetic is done in code
here (build_evidence); the models only get judgment and language.
"""
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from backend.shared.llm import LLM
from backend.shared.settings import Settings

from .config import MAX_BRIEF_ATTEMPTS, MAX_BRIEF_WORDS

WRITE_VERSION = "write_brief_v1"
JUDGE_VERSION = "judge_brief_v1"
WRITE_SYSTEM = (Path(__file__).parent / "prompts" / f"{WRITE_VERSION}.md").read_text()
JUDGE_SYSTEM = (Path(__file__).parent / "prompts" / f"{JUDGE_VERSION}.md").read_text()


class Brief(BaseModel):
    headline: str
    explanation: str = Field(description="<= 80 words, plain language")
    suggested_action: str


class Verdict(BaseModel):
    passed: bool
    issues: list[str] = []


def build_evidence(insight: dict) -> dict:
    """The hard numbers the brief must be true to. Pure code."""
    return {
        "insight_id": insight["insight_id"],
        "product_name": insight["product_name"],
        "segment": insight.get("segment") or {},
        "orders": insight["orders"],
        "returns": insight["returns"],
        "return_rate_pct": round(insight["return_rate"] * 100, 1),
        "baseline_rate_pct": round(insight["baseline_rate"] * 100, 1),
        "lift": insight["lift"],
        "reason_breakdown": insight.get("reason_breakdown") or {},
        "sample_comments": (insight.get("sample_comments") or [])[:5],
    }


def deterministic_checks(brief: Brief, insight: dict) -> list[str]:
    """Free, exact checks before spending a judge call."""
    ev = build_evidence(insight)
    issues: list[str] = []
    text = f"{brief.headline} {brief.explanation}".lower()
    if ev["product_name"].lower() not in text:
        issues.append("Brief does not name the product.")
    rate = str(ev["return_rate_pct"])
    if rate not in brief.explanation and str(int(ev["return_rate_pct"])) not in brief.explanation \
            and str(ev["returns"]) not in brief.explanation:
        issues.append("Explanation cites no return-rate number from the evidence.")
    if len(brief.explanation.split()) > MAX_BRIEF_WORDS:
        issues.append(f"Explanation is longer than {MAX_BRIEF_WORDS} words.")
    if not brief.suggested_action.strip():
        issues.append("No suggested action.")
    return issues


def generate_brief(llm: LLM, settings: Settings, insight: dict) -> dict:
    ev = build_evidence(insight)
    evidence_json = json.dumps(ev, ensure_ascii=False)
    cost, feedback, open_issues = 0.0, "", []
    start = time.perf_counter()
    brief = None
    for attempt in range(1, MAX_BRIEF_ATTEMPTS + 1):
        user = f"<evidence>\n{evidence_json}\n</evidence>"
        if feedback:
            user += f"\n<reviewer_feedback>\n{feedback}\n</reviewer_feedback>"
        try:
            w = llm.parse(model=settings.model_returns_strong, system=WRITE_SYSTEM, user=user,
                          output_format=Brief, max_tokens=800, temperature=0.3)
        except Exception as e:
            return _manual(insight, {}, [f"writer unavailable: {e}"], attempt, cost, start, settings)
        cost += w.cost_usd
        brief = w.parsed

        issues = deterministic_checks(brief, insight)
        if issues:
            open_issues, feedback = issues, "; ".join(issues)
            continue

        try:
            v = llm.parse(model=settings.model_fast, system=JUDGE_SYSTEM,
                          user=f"<evidence>\n{evidence_json}\n</evidence>\n<brief>\n{brief.model_dump_json()}\n</brief>",
                          output_format=Verdict, max_tokens=256, temperature=0)
        except Exception as e:
            return _manual(insight, brief.model_dump(), [f"judge unavailable: {e}"], attempt, cost, start, settings)
        cost += v.cost_usd
        if v.parsed.passed:
            return _result(insight, brief.model_dump(), "passed_checks", [], attempt, cost, start, settings)
        open_issues, feedback = v.parsed.issues, "; ".join(v.parsed.issues)

    return _manual(insight, brief.model_dump() if brief else {}, open_issues, MAX_BRIEF_ATTEMPTS, cost, start, settings)


def _result(insight, brief, status, issues, attempts, cost, start, settings):
    return {"insight_id": insight["insight_id"], "product_id": insight.get("product_id"),
            "product_name": insight["product_name"], "brief": brief, "status": status,
            "open_issues": issues, "attempts": attempts, "model": settings.model_returns_strong,
            "cost_usd": round(cost, 6), "latency_ms": int((time.perf_counter() - start) * 1000)}


def _manual(insight, brief, issues, attempts, cost, start, settings):
    return _result(insight, brief, "needs_manual_review", issues, attempts, cost, start, settings)

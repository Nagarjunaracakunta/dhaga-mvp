"""LLM #2 (strong model) + evaluator-optimizer loop. Code supplies verified evidence; model only writes."""
import json
from typing import Optional

from . import config
from .evaluator import deterministic_checks
from .llm import AuthError, ModelSpec, structured_chain, invoke_tracked
from .mock import mock_recommender, mock_judge
from .prompts import RECOMMEND_PROMPT, JUDGE_PROMPT
from .schemas import Recommendation, Verdict

_SKIP = ("UNSPECIFIED/", "UNCLEAR/", "UNCLASSIFIED/")


def build_evidence(ins: dict) -> dict:
    n = ins["returns"]
    reasons = [{"reason": k, "count": v, "share_of_returns_pct": round(v / n * 100, 1)}
               for k, v in ins["reason_detail_breakdown"].items() if not k.startswith(_SKIP)][:3]
    return {
        "product": ins["product_name"], "segment": ins["segment"],
        "orders": ins["orders"], "returns": n,
        "return_rate_pct": round(ins["return_rate"] * 100, 1),
        "overall_return_rate_pct": round(ins["baseline_rate"] * 100, 1),
        "lift_vs_overall": ins["lift"],
        "top_reasons": reasons,
        "body_areas": [{"area": k, "count": v} for k, v in list(ins["body_area_breakdown"].items())[:3]],
        "unclassified_share_pct": round(ins["unclassified_share"] * 100, 1),
    }


def _chain(prompt, schema, spec, mock, fallback=None, temperature=0.0):
    return mock if spec.provider == "mock" else structured_chain(prompt, schema, spec, fallback, temperature)


def generate_validated_recommendation(ins: dict, strong: ModelSpec, judge_spec: ModelSpec, tracker,
                                      use_judge=True, max_attempts=config.MAX_REC_ATTEMPTS,
                                      rec_chain=None, judge_chain=None, fallback: Optional[ModelSpec] = None) -> dict:
    ev = build_evidence(ins)
    ev_json = json.dumps(ev, ensure_ascii=False)
    rec_chain = rec_chain or _chain(RECOMMEND_PROMPT, Recommendation, strong, mock_recommender, fallback, config.TEMP_WRITER)
    judge_chain = judge_chain or _chain(JUDGE_PROMPT, Verdict, judge_spec, mock_judge, fallback, config.TEMP_JUDGE)
    issues, rec, attempts = [], None, 0
    for attempts in range(1, max_attempts + 1):
        if tracker.over_budget():
            issues = issues or ["Budget exhausted before a recommendation was produced"]
            break
        feedback = "\n".join(f"- {i}" for i in issues) or "(none)"
        try:
            rec = invoke_tracked(rec_chain, {"evidence_json": ev_json, "feedback": feedback}, strong, tracker)
        except AuthError:
            raise
        except Exception as e:
            issues = [f"Model call failed: {e}"]
            continue
        if rec is None:
            issues = ["Model output did not match the schema"]
            continue
        issues = deterministic_checks(rec, ev)                       # free, exact
        if not issues and use_judge:                                  # cheap LLM judge, only if code checks pass
            try:
                v = invoke_tracked(judge_chain, {"evidence_json": ev_json, "headline": rec.headline,
                                                 "explanation": rec.explanation, "action": rec.suggested_action},
                                   judge_spec, tracker)
                issues = [] if (v and v.passed) else (v.issues if v else ["Judge output invalid"])
            except AuthError:
                raise
            except Exception as e:
                issues = [f"Judge call failed: {e}"]
        if not issues:
            break
    return {
        "insight_id": ins["insight_id"], "evidence": ev,
        "status": "passed_checks" if (rec and not issues) else "needs_manual_review",
        "attempts": attempts, "open_issues": issues,
        "recommendation": rec.model_dump() if rec else None,
    }

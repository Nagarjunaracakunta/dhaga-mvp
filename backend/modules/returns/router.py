"""Returns Insights API. Mounted at /api/returns."""
import json
import threading
from functools import lru_cache
from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.shared.errors import AppError, NotFound
from backend.shared.llm import get_llm
from backend.shared.settings import get_settings

from . import aggregation, classifier
from .pipeline import run_pipeline
from .store import MemoryStore, SupabaseStore

router = APIRouter(tags=["returns"])
_cache = {}
_lock = threading.RLock()


@lru_cache
def get_store():
    return SupabaseStore() if get_settings().returns_mode == "supabase" else MemoryStore()


def _result(refresh: bool = False):
    with _lock:  # page loads fire several requests at once; build the pipeline result only once
        if refresh or "res" not in _cache:
            _cache["res"] = run_pipeline(source=get_settings().returns_mode, store=get_store())
        return _cache["res"]


def _records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


@router.get("/summary")
def summary(refresh: bool = False):
    return _result(refresh).summary


@router.get("/products")
def products():
    r = _result()
    return _records(aggregation.product_table(r.orders, r.returns))


@router.get("/breakdown")
def breakdown(by: str = Query("size", pattern="^(size|colour|category|product_id)$")):
    r = _result()
    return _records(aggregation.by_dimension(r.orders, r.returns, [by]))


@router.get("/reasons")
def reasons(product_id: Optional[str] = None):
    r = _result()
    df = r.returns if not product_id else r.returns[r.returns["product_id"] == product_id]
    return _records(aggregation.reason_counts(df))


@router.get("/insights")
def candidate_insights():
    return _result().candidate_insights


@router.get("/records")
def records(
    needs_llm: Optional[bool] = None,
    product_id: Optional[str] = None,
    limit: int = 100
):
    df = _result().returns
    if needs_llm is not None:
        df = df[df["needs_llm"] == needs_llm]
    if product_id:
        df = df[df["product_id"] == product_id]
    return _records(df.head(limit))


@router.get("/rejected")
def rejected():
    return _records(_result().rejected)


# ---------------- Stage 2: classify "Other" comments, then a person reviews ----------------
class ClassifyRequest(BaseModel):
    limit: int = 300          # cap one run; each comment costs about $0.001
    redo: bool = False        # re-classify comments that already have an AI reason


@router.post("/classify")
def classify(body: ClassifyRequest = ClassifyRequest()):
    """Classify "Other" return comments with Haiku 4.5 (in parallel) and save the reasons."""
    s = get_settings()
    df = _result(refresh=True).returns
    states = ["pending_llm", "ai", "ai_review"] if body.redo else ["pending_llm"]
    todo = df[df["classification_source"].isin(states)].head(body.limit)
    if todo.empty:
        return {"classified": 0, "failed": 0, "cost_usd": 0.0, "message": "Nothing waiting to classify"}
    run = classifier.classify_comments(get_llm(), s, dict(zip(todo["return_id"], todo["return_comment"])))
    if run["failed"] and not run["results"]:
        reason = next(iter(run["failed"].values()))
        raise AppError("CLASSIFIER_UNAVAILABLE", f"No comments could be classified: {reason}", 503)
    get_store().save_ai(run["results"], df)
    review = sum(classifier.needs_review(r["ai_category"], r["ai_confidence"]) for r in run["results"].values())
    get_store().log_run({"model_name": run["model"], "prompt_version": run["prompt_version"],
                         "input_summary": f"{len(todo)} Other return comments",
                         "output": {"classified": len(run["results"]), "failed": len(run["failed"]),
                                    "needs_review": review, "cost_usd": run["cost_usd"]},
                         "evaluation_status": "REVIEW_REQUIRED" if review else "PASSED",
                         "processing_time_ms": run["latency_ms"]})
    _result(refresh=True)
    return {"classified": len(run["results"]), "failed": len(run["failed"]), "needs_review": review,
            "cost_usd": run["cost_usd"], "latency_ms": run["latency_ms"],
            "failed_examples": list(run["failed"].values())[:3]}


@router.get("/review-queue")
def review_queue(include_confident: bool = False, limit: int = 100):
    """AI reasons waiting for a person: low confidence or unclear (or all AI reasons, if asked)."""
    df = _result().returns
    states = ["ai_review", "ai"] if include_confident else ["ai_review"]
    q = df[df["classification_source"].isin(states)].copy()
    q["ai_confidence"] = q["ai_confidence"].astype(float)
    q = q.sort_values("ai_confidence").head(limit)
    cols = ["return_id", "product_name", "size", "colour", "return_comment", "ai_category", "ai_subcategory",
            "ai_confidence", "classification_source"]
    return _records(q[[c for c in cols if c in q.columns]])


class ReviewRequest(BaseModel):
    category: Literal["FIT", "COLOUR", "QUALITY", "DAMAGE", "WRONG_ITEM", "CHANGED_MIND", "UNCLEAR"]


@router.post("/{return_id}/review")
def review(return_id: str, body: ReviewRequest):
    """A person accepts the AI reason (send the same category) or corrects it."""
    df = _result().returns
    row = df[df["return_id"] == return_id]
    if row.empty:
        raise NotFound("RETURN_NOT_FOUND", f"No return {return_id}")
    get_store().set_final(return_id, body.category, df)
    _result(refresh=True)
    return {"return_id": return_id, "final_category": body.category,
            "action": "accepted" if body.category == row.iloc[0].get("ai_category") else "corrected"}

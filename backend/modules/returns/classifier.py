"""Stage 2: read the "Other" comment on a return and give it a real reason (Haiku 4.5, temperature 0).

Comments are independent of each other, so they run through one LangChain chain with .batch(),
8 at a time (parallelization pattern).
Results are saved to the returns table (ai_category / ai_subcategory / ai_confidence); a person can
accept or correct each one (final_category). The pipeline then uses them in place of "UNCLASSIFIED".
"""
import time
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from backend.shared.llm import LLM, LLMUnavailable, parse_many
from backend.shared.settings import Settings

from .config import ESCALATE_BELOW, MAX_ESCALATION_SHARE

PROMPT_VERSION = "classify_return_v2"
SYSTEM = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text()
CATEGORIES = ["FIT", "COLOUR", "QUALITY", "DAMAGE", "WRONG_ITEM", "CHANGED_MIND", "UNCLEAR"]
REVIEW_BELOW = 0.70  # confidence under this goes to the review queue
MAX_WORKERS = 8


class ReturnClassification(BaseModel):
    category: Literal["FIT", "COLOUR", "QUALITY", "DAMAGE", "WRONG_ITEM", "CHANGED_MIND", "UNCLEAR"]
    sub_reason: Literal["TOO_TIGHT", "TOO_LOOSE", "TOO_SHORT", "TOO_LONG", "LISTING_DIFFERENCE", "FABRIC",
                        "STITCHING", "NONE"]
    body_area: Literal["SHOULDERS", "BUST", "WAIST", "SLEEVES", "LENGTH", "OVERALL", "NONE"]
    confidence: float = Field(description="0 to 1")


def subcategory(c: ReturnClassification) -> Optional[str]:
    """Stored in ai_subcategory as e.g. 'TOO_TIGHT:SHOULDERS'."""
    if c.sub_reason == "NONE":
        return None
    return f"{c.sub_reason}:{c.body_area}" if c.body_area != "NONE" else c.sub_reason


def needs_review(category: Optional[str], confidence) -> bool:
    try:
        return category == "UNCLEAR" or float(confidence) < REVIEW_BELOW
    except (TypeError, ValueError):
        return True


def classify_comments(llm: LLM, settings: Settings, comments: dict[str, str]) -> dict:
    """comments: {return_id: text}. One LangChain chain run over all comments with .batch(),
    MAX_WORKERS at a time (parallelization). Returns results, failures, cost and time."""
    ids = list(comments)
    start = time.perf_counter()
    outputs = parse_many(llm, model=settings.model_fast, system=SYSTEM,
                         users=[f"<comment>\n{comments[rid]}\n</comment>" for rid in ids],
                         output_format=ReturnClassification, max_tokens=256, temperature=0,
                         max_concurrency=MAX_WORKERS)
    results, failed, cost = {}, {}, 0.0
    for rid, out in zip(ids, outputs):
        if isinstance(out, LLMUnavailable):
            failed[rid] = f"unavailable: {out}"
        elif isinstance(out, Exception):
            failed[rid] = str(out)
        else:
            c = out.parsed
            c.confidence = min(max(c.confidence, 0.0), 1.0)
            results[rid] = {"ai_category": c.category, "ai_subcategory": subcategory(c),
                            "ai_confidence": round(c.confidence, 4)}
            cost += out.cost_usd

    # Routing: retry the least-confident answers on the stronger model, capped at a share of the run
    # (but allow at least one, so small runs and the single-comment demo can still escalate).
    cap = max(1, int(len(ids) * MAX_ESCALATION_SHARE))
    uncertain = sorted((rid for rid in results if results[rid]["ai_confidence"] < ESCALATE_BELOW),
                       key=lambda r: results[r]["ai_confidence"])[:cap]
    escalated = 0
    for rid in uncertain:
        try:
            out = llm.parse(model=settings.model_returns_strong, system=SYSTEM,
                            user=f"<comment>\n{comments[rid]}\n</comment>",
                            output_format=ReturnClassification, max_tokens=256, temperature=0)
        except Exception:        # strong model down -> keep the fast answer, stay visible
            continue
        cost += out.cost_usd
        escalated += 1
        c = out.parsed
        c.confidence = min(max(c.confidence, 0.0), 1.0)
        if round(c.confidence, 4) >= results[rid]["ai_confidence"]:
            results[rid] = {"ai_category": c.category, "ai_subcategory": subcategory(c),
                            "ai_confidence": round(c.confidence, 4)}

    return {"results": results, "failed": failed, "cost_usd": round(cost, 6),
            "latency_ms": int((time.perf_counter() - start) * 1000), "model": settings.model_fast,
            "strong_model": settings.model_returns_strong, "escalated": escalated,
            "prompt_version": PROMPT_VERSION}


def apply_classifications(returns: pd.DataFrame) -> pd.DataFrame:
    """Use saved AI/human reasons for "Other" returns. Expects optional columns ai_category, ai_subcategory,
    ai_confidence, final_category (from Supabase or the in-memory store)."""
    df = returns.copy()
    for col in ["ai_category", "ai_subcategory", "ai_confidence", "final_category"]:
        if col not in df.columns:
            df[col] = None
    pending = df["classification_source"] == "pending_llm"
    human = pending & df["final_category"].notna() & (df["final_category"].astype(str) != "")
    ai = pending & ~human & df["ai_category"].notna() & (df["ai_category"].astype(str) != "")

    def split(sub):
        if not isinstance(sub, str) or not sub:
            return None, None
        reason, _, area = sub.partition(":")
        return reason, (area or None)

    for idx in df.index[ai | human]:
        reason, area = split(df.at[idx, "ai_subcategory"])
        if human[idx]:
            df.at[idx, "primary_reason"] = df.at[idx, "final_category"]
            same = df.at[idx, "final_category"] == df.at[idx, "ai_category"]
            df.at[idx, "sub_reason"] = reason if same else None
            df.at[idx, "body_area"] = area if same else None
            df.at[idx, "classification_source"] = "human"
        else:
            df.at[idx, "primary_reason"] = df.at[idx, "ai_category"]
            df.at[idx, "sub_reason"] = reason
            df.at[idx, "body_area"] = area
            df.at[idx, "classification_source"] = ("ai_review" if needs_review(df.at[idx, "ai_category"],
                                                                               df.at[idx, "ai_confidence"]) else "ai")
    df["needs_llm"] = df["classification_source"] == "pending_llm"
    return df

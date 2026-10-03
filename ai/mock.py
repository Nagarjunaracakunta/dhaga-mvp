"""Offline stand-ins ("mock" provider) so the whole flow runs and is testable without API keys.
Keyword rules only - NOT a measure of real accuracy."""
import json
import re
from langchain_core.runnables import RunnableLambda
from .schemas import BatchOutput, ItemClassification, Recommendation, Verdict
from .taxonomy import Primary, Sub, BodyArea


def _has(t, *words):
    return any(w in t for w in words)


def mock_rule(comment: str):
    t = comment.lower()
    area = BodyArea.NONE
    if _has(t, "galat", "wrong item", "different product", "order ye nahi"):
        return Primary.WRONG_ITEM, Sub.UNSPECIFIED, area, 0.9
    if _has(t, "phata", "stain", "toote", "damage", "torn"):
        return Primary.DAMAGE, Sub.UNSPECIFIED, area, 0.9
    if _has(t, "mann badal", "cancel", "don't need", "dont need", "anymore"):
        return Primary.CHANGED_MIND, Sub.UNSPECIFIED, area, 0.85
    if _has(t, "stitch", "thread", "seam"):
        return Primary.QUALITY, Sub.STITCHING, area, 0.9
    if _has(t, "colour", "color", "rang"):
        return Primary.COLOUR, Sub.LISTING_DIFFERENCE, area, 0.85
    if _has(t, "fabric", "kapda", "material", "cheap", "quality", "thin"):
        return Primary.QUALITY, Sub.FABRIC, area, 0.85
    if _has(t, "length", "short", "long", "lambi", "chhoti"):
        sub = Sub.TOO_SHORT if _has(t, "short", "chhoti", "kam") else Sub.TOO_LONG
        return Primary.FIT, sub, BodyArea.LENGTH, 0.8
    if _has(t, "shoulder", "kandh"):
        area = BodyArea.SHOULDERS
    elif _has(t, "waist", "kamar"):
        area = BodyArea.WAIST
    elif _has(t, "bust", "chest", "chhati"):
        area = BodyArea.BUST
    if _has(t, "tight", "snug"):
        return Primary.FIT, Sub.TOO_TIGHT, area, 0.9
    if _has(t, "loose", "dhila", "baggy", "bada"):
        return Primary.FIT, Sub.TOO_LOOSE, area, 0.85
    return Primary.UNCLEAR, Sub.UNCLEAR, area, 0.3


def _classify(payload: dict):
    items = json.loads(payload["items_json"])
    out = []
    for it in items:
        p, s, a, c = mock_rule(it["comment"])
        out.append(ItemClassification(id=it["id"], primary_reason=p, sub_reason=s, body_area=a, confidence=c))
    return {"raw": None, "parsed": BatchOutput(items=out), "parsing_error": None}


def _recommend(payload: dict):
    ev = json.loads(payload["evidence_json"])
    seg = ", ".join(f"{k} {v}" for k, v in ev["segment"].items())
    top = ev["top_reasons"][0] if ev["top_reasons"] else None
    reason = f" {top['reason'].replace('/', ' / ').lower()}" if top else ""
    expl = (f"{ev['returns']} of {ev['orders']} orders ({ev['return_rate_pct']}%) were returned, versus "
            f"{ev['overall_return_rate_pct']}% overall.")
    if top:
        expl += f" The most common reason is{reason}: {top['count']} returns ({top['share_of_returns_pct']}%)."
    return {"raw": None, "parsing_error": None, "parsed": Recommendation(
        headline=f"Investigate {ev['product']}" + (f" ({seg})" if seg else ""),
        explanation=expl,
        suggested_action="Review the product listing and measurements for this segment against the returned-item comments.")}


def _judge(payload: dict):
    return {"raw": None, "parsed": Verdict(passed=True, issues=[]), "parsing_error": None}


mock_classifier = RunnableLambda(_classify)
mock_recommender = RunnableLambda(_recommend)
mock_judge = RunnableLambda(_judge)

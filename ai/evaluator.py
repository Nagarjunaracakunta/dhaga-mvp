"""Evaluator for LLM #2. Cheap deterministic checks FIRST (free, exact); LLM judge only if those pass."""
import re
from . import config

_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def allowed_numbers(ev: dict) -> set:
    nums = {ev["orders"], ev["returns"], ev["return_rate_pct"], ev["overall_return_rate_pct"], ev["lift_vs_overall"]}
    for r in ev["top_reasons"]:
        nums |= {r["count"], r["share_of_returns_pct"]}
    for b in ev["body_areas"]:
        nums.add(b["count"])
    out = set()
    for n in nums:
        out |= {round(float(n), 2), round(float(n), 1), float(round(float(n)))}
    return out


def check_numbers(text: str, ev: dict) -> list:
    allowed = allowed_numbers(ev)
    bad = [n for n in _NUM.findall(_QUOTED.sub("", text)) if round(float(n), 2) not in allowed]
    return [f"Number {n} is not in the evidence" for n in dict.fromkeys(bad)]


def deterministic_checks(rec, ev: dict) -> list:
    text = f"{rec.headline} {rec.explanation} {rec.suggested_action}"
    issues = check_numbers(text, ev)
    if ev["product"].lower() not in (rec.headline + " " + rec.explanation).lower():
        issues.append(f"Product name '{ev['product']}' is not mentioned")
    if len(rec.explanation.split()) > config.MAX_EXPLANATION_WORDS:
        issues.append(f"Explanation longer than {config.MAX_EXPLANATION_WORDS} words")
    if not rec.suggested_action.strip():
        issues.append("Missing suggested action")
    return issues

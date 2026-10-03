"""Estimate LLM cost BEFORE spending anything:  python -m ai.estimate [--fast p:m] [--strong p:m]
Token sizes are rough heuristics (chars/4); prices come from ai/config.py. Compare against the real report after a run."""
import argparse
import math
from . import config
from .classifier import normalize_comment, is_junk
from .llm import ModelSpec, specs_from_env
from .prompts import CLASSIFY_SYSTEM
from backend.pipeline import run_pipeline

OUT_TOKENS_PER_ITEM = 28
ESCALATION_RATE = 0.10


def _price(spec):
    return config.PRICES_PER_MTOK.get(spec.model, (0.0, 0.0))


def estimate(fast: ModelSpec, strong: ModelSpec) -> dict:
    res = run_pipeline()
    pending = res.returns[res.returns["needs_llm"]]["return_comment"].tolist()
    uniq = {normalize_comment(c): c for c in pending}
    todo = [c for c in uniq.values() if not is_junk(c)]
    sys_tok = len(CLASSIFY_SYSTEM) // 4
    item_tok = [len(c) // 4 + 12 for c in todo]
    calls = math.ceil(len(todo) / config.BATCH_SIZE)

    def cost(spec, n_calls, n_items, in_items):
        pi, po = _price(spec)
        return (n_calls * sys_tok + sum(in_items)) / 1e6 * pi + n_items * OUT_TOKENS_PER_ITEM / 1e6 * po

    n_esc = math.ceil(len(todo) * ESCALATION_RATE)
    optimized = (cost(fast, calls, len(todo), item_tok)
                 + cost(strong, math.ceil(n_esc / config.BATCH_SIZE), n_esc, item_tok[:n_esc]))
    naive = cost(strong, len(pending), len(pending), [len(c) // 4 + 12 for c in pending])
    return {
        "other_with_comment_rows": len(pending), "unique_comments": len(uniq), "junk_skipped": len(uniq) - len(todo),
        "batch_calls_fast_model": calls, "assumed_escalation_rate": ESCALATION_RATE,
        "optimized_estimate_usd": round(optimized, 4),
        "naive_one_call_per_row_strong_model_usd": round(naive, 4),
        "saving_x": round(naive / optimized, 1) if optimized else None,
        "note": "Heuristic token counts; prices from ai/config.py (verify). Real usage is reported by `python -m ai.run`.",
    }


# ---- Dhaga-scale arithmetic ----
BRIEF = {"orders_per_week": 48_000, "return_rate": 0.31, "other_share": 0.44}   # stated in the brief


def weekly_cost(fast: ModelSpec, strong: ModelSpec, comment_rate=0.9, unique_ratio=0.7, escalation=ESCALATION_RATE,
                top_k=config.TOP_K_INSIGHTS, attempts=1.5, usd_inr=88.0) -> list:
    """Returns printable lines. [brief] = stated in the case study, [assumed] = our estimate (change the flags)."""
    res = run_pipeline()
    pend = res.returns[res.returns["needs_llm"]]["return_comment"]
    item_tok = float((pend.str.len() / 4 + 12).mean())
    sys_tok = len(CLASSIFY_SYSTEM) // 4
    pf, ps = _price(fast), _price(strong)
    o = BRIEF["orders_per_week"]; ret = o * BRIEF["return_rate"]; other = ret * BRIEF["other_share"]
    withc = other * comment_rate; uniq = withc * unique_ratio
    calls = math.ceil(uniq / config.BATCH_SIZE)
    in_f, out_f = calls * sys_tok + uniq * item_tok, uniq * OUT_TOKENS_PER_ITEM
    usd_cls = in_f / 1e6 * pf[0] + out_f / 1e6 * pf[1]
    n_esc = uniq * escalation; calls_s = math.ceil(n_esc / config.BATCH_SIZE)
    usd_esc = (calls_s * sys_tok + n_esc * item_tok) / 1e6 * ps[0] + n_esc * OUT_TOKENS_PER_ITEM / 1e6 * ps[1]
    rec_in, rec_out, jud_in, jud_out = 900, 150, 1100, 60       # assumed tokens per attempt
    usd_rec = top_k * attempts * ((rec_in / 1e6 * ps[0] + rec_out / 1e6 * ps[1]) + (jud_in / 1e6 * pf[0] + jud_out / 1e6 * pf[1]))
    total = usd_cls + usd_esc + usd_rec
    naive = other * (sys_tok + item_tok) / 1e6 * ps[0] + other * OUT_TOKENS_PER_ITEM / 1e6 * ps[1]
    return [
        f"orders per week                         {o:,.0f}   [brief]",
        f"x return rate {BRIEF['return_rate']:.0%}                       = {ret:,.0f} returns/week   [brief]",
        f"x 'Other' share {BRIEF['other_share']:.0%}                     = {other:,.0f} 'Other' returns/week   [brief]",
        f"x with a comment {comment_rate:.0%}                    = {withc:,.0f} comments/week   [assumed]",
        f"x unique {unique_ratio:.0%} (dedupe, real text)         = {uniq:,.0f} to classify/week   [assumed]",
        f"/ {config.BATCH_SIZE} per call                         = {calls} fast-model calls; ~{item_tok:.0f} tokens/comment (measured on demo text), {sys_tok} system tokens/call",
        f"classification ({fast.label})   = ${usd_cls:.3f}",
        f"escalation {escalation:.0%} to {strong.label} = ${usd_esc:.3f}   [assumed rate]",
        f"{top_k} briefs x {attempts} attempts (writer + judge)   = ${usd_rec:.3f}   [assumed tokens]",
        f"ONE WEEKLY RUN                           = ${total:.2f}  = Rs {total * usd_inr:,.0f}   (at Rs {usd_inr:.0f}/USD [assumed])",
        f"per 1,000 'Other' returns                = ${total / other * 1000:.3f}",
        f"per year (x52)                           = ${total * 52:,.0f}  = Rs {total * 52 * usd_inr:,.0f}",
        f"naive baseline (1 strong call per row)   = ${naive:.2f}/week  ({naive / total:.0f}x more)",
        "prices are budgeting estimates from ai/config.py - verify before quoting to the client",
    ]


if __name__ == "__main__":
    f, s, _ = specs_from_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", default=f.label); ap.add_argument("--strong", default=s.label)
    ap.add_argument("--weekly", action="store_true", help="scale to Dhaga's volume with the arithmetic shown")
    ap.add_argument("--comment-rate", type=float, default=0.9); ap.add_argument("--unique-ratio", type=float, default=0.7)
    ap.add_argument("--usd-inr", type=float, default=88.0)
    a = ap.parse_args()
    fs, ss = ModelSpec.parse(a.fast), ModelSpec.parse(a.strong)
    if a.weekly:
        print("\n".join(weekly_cost(fs, ss, a.comment_rate, a.unique_ratio, usd_inr=a.usd_inr)))
    else:
        for k, v in estimate(fs, ss).items():
            print(f"{k:42} {v}")

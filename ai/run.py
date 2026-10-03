"""Stage 2 entrypoint:  python -m ai.run [--limit 50] [--eval] [--fast p:m] [--strong p:m]
validate/normalize (code) -> classify "Other" comments (LLM #1) -> re-aggregate + find insights (code)
-> recommend (LLM #2) -> evaluate (code + cheap LLM judge) -> outputs for human review."""
import argparse
import json
import logging

from . import config
from .apply import apply_classifications
from .cache import ClassificationCache
from .classifier import classify_comments
from .classifier_eval import evaluate
from .cost import CostTracker
from .llm import AuthError, ModelSpec, PROVIDER_DEFAULTS, check_credentials, specs_from_env
from .recommender import generate_validated_recommendation
from backend import config as bconfig
from backend import aggregation
from backend.insights import find_candidate_insights
from backend.pipeline import run_pipeline
from db import store


def run(fast: ModelSpec, strong: ModelSpec, fallback=None, limit=None, escalate=True, use_judge=True,
        top_k=config.TOP_K_INSIGHTS, use_cache=True, max_usd=config.MAX_USD_DEFAULT,
        max_calls=config.MAX_CALLS_DEFAULT, with_eval=False, out_dir=bconfig.PROCESSED_DIR, cache_path=None, engine=None,
        data_dir=bconfig.DATA_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker(max_usd, max_calls)
    if not use_cache:
        cache = None
    elif engine is not None:
        cache = store.DbCache(engine)            # shared, persistent cache (Postgres/Supabase or local SQLite db)
    else:
        cache = ClassificationCache(cache_path or out_dir / "llm_cache.sqlite")

    base = run_pipeline(data_dir)                                           # code: validate + normalize + aggregate
    pending = base.returns.loc[base.returns["needs_llm"], "return_comment"].tolist()
    results, cstats = classify_comments(pending, fast, strong, tracker, cache, escalate=escalate,
                                        limit=limit, fallback=fallback)               # LLM #1
    returns, applied = apply_classifications(base.returns, results)                   # code
    insights = find_candidate_insights(base.orders, returns)                          # code
    recs = []
    for ins in insights[:top_k]:                                                      # LLM #2 + evaluator
        recs.append({"insight": ins, **generate_validated_recommendation(
            ins, strong, fast, tracker, use_judge=use_judge, fallback=fallback)})

    report = {"models": {"fast": fast.label, "strong": strong.label, "fallback": fallback.label if fallback else None},
              "classification": dict(cstats), "applied": applied, "cost": tracker.report(),
              "recommendations": {"generated": len(recs),
                                  "passed_checks": sum(r["status"] == "passed_checks" for r in recs),
                                  "needs_manual_review": sum(r["status"] != "passed_checks" for r in recs)}}
    report["pipeline"] = base.summary
    report["by_product"] = aggregation.by_dimension(base.orders, returns, ["product_id", "product_name"]).to_dict("records")
    report["by_size"] = aggregation.by_dimension(base.orders, returns, ["size"]).to_dict("records")
    report["rejected_by_reason"] = (base.rejected.groupby(["source", "reason"]).size().reset_index(name="count").to_dict("records")
                                    if len(base.rejected) else [])
    report["rejected_sample"] = base.rejected.head(200).to_dict("records")
    if with_eval:
        report["classifier_eval"] = evaluate(returns)
    if engine is not None:
        run_id = store.new_run_id()
        report["run_id"] = run_id
        store.save_run(engine, run_id, fast.label, strong.label, report)
        store.save_returns(engine, returns, run_id)
        store.save_insights(engine, run_id, recs)
    returns.to_csv(out_dir / "returns_classified.csv", index=False)
    (out_dir / "ai_insights.json").write_text(json.dumps(recs, indent=2, default=str))
    (out_dir / "ai_run_report.json").write_text(json.dumps(report, indent=2, default=str))
    return returns, recs, report


def main():
    f, s, fb = specs_from_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), help="use that provider's default fast/strong models")
    ap.add_argument("--fast"); ap.add_argument("--strong")
    ap.add_argument("--fallback", default=fb.label if fb else None)
    ap.add_argument("--limit", type=int, help="max unique comments to classify (use small values for a first real run)")
    ap.add_argument("--top-k", type=int, default=config.TOP_K_INSIGHTS)
    ap.add_argument("--max-usd", type=float, default=config.MAX_USD_DEFAULT)
    ap.add_argument("--max-calls", type=int, default=config.MAX_CALLS_DEFAULT)
    ap.add_argument("--no-escalate", action="store_true"); ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--no-cache", action="store_true"); ap.add_argument("--eval", action="store_true")
    ap.add_argument("--db", action="store_true", help="persist to DATABASE_URL (Supabase/Postgres) or local SQLite if unset")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    dflt = PROVIDER_DEFAULTS.get(a.provider, (f.label, s.label))
    fast, strong = ModelSpec.parse(a.fast or dflt[0]), ModelSpec.parse(a.strong or dflt[1])
    fallback = ModelSpec.parse(a.fallback) if a.fallback else None
    print(f"Models: fast={fast.label}  strong={strong.label}" + (f"  fallback={fallback.label}" if fallback else ""))
    try:
        check_credentials(fast, strong, *([fallback] if fallback else []))
    except AuthError as e:
        raise SystemExit(f"\nERROR: {e}")
    engine = None
    if a.db:
        engine = store.get_engine()
        store.init_schema(engine)
    try:
        _, recs, report = run(fast, strong, fallback, a.limit, not a.no_escalate, not a.no_judge, a.top_k,
                              not a.no_cache, a.max_usd, a.max_calls, a.eval, engine=engine)
    except AuthError as e:
        raise SystemExit(f"\nERROR: {e}")
    print(json.dumps(report, indent=2, default=str))
    print("\n=== RECOMMENDATIONS (for human review) ===")
    for r in recs:
        rec = r["recommendation"] or {}
        print(f"\n[{r['status']}, attempts={r['attempts']}] {rec.get('headline')}\n  {rec.get('explanation')}\n  -> {rec.get('suggested_action')}")
        if r["open_issues"]:
            print("  open issues:", r["open_issues"])


if __name__ == "__main__":
    main()

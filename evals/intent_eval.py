"""How often does Copilot pick the right intent? Scores the classifier against data/cx_eval/tickets_labelled.csv.

    python evals/intent_eval.py               # 10 tickets per intent with the configured model (~$0.07)
    python evals/intent_eval.py --per-intent 20
    python evals/intent_eval.py --fallback-only   # keyword fallback on all tickets, free

Also scores the safety outcome that matters most: did a ticket that needs a person get routed to one?
Results are written to evals/results/.
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.modules.cx import classifier, fallback  # noqa: E402
from backend.shared.llm import LLMOutputError, LLMUnavailable, get_llm  # noqa: E402
from backend.shared.settings import get_settings  # noqa: E402

LABELLED = ROOT / "data" / "cx_eval" / "tickets_labelled.csv"
RESULTS = ROOT / "evals" / "results"
NEEDS_PERSON = {"DELIVERED_NOT_RECEIVED", "DAMAGED_OR_WRONG_ITEM", "OTHER"}  # always routed to a human by the rules


def score(rows, predict):
    hits, by_intent, misses, unsafe = 0, defaultdict(lambda: [0, 0]), [], 0
    for r in rows:
        got = predict(r)
        ok = got == r["expected_intent"]
        hits += ok
        by_intent[r["expected_intent"]][0] += ok
        by_intent[r["expected_intent"]][1] += 1
        if not ok:
            misses.append({"message": r["message"], "expected": r["expected_intent"], "got": got})
            # Unsafe miss: a ticket that needs a person was given an intent that leads to an automatic draft
            if r["expected_intent"] in NEEDS_PERSON and got not in NEEDS_PERSON:
                unsafe += 1
    return {
        "n": len(rows), "accuracy": round(hits / len(rows), 4),
        "per_intent": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_intent.items())},
        "unsafe_misses": unsafe, "misses": misses,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-intent", type=int, default=10)
    ap.add_argument("--fallback-only", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rows = list(csv.DictReader(LABELLED.open()))
    RESULTS.mkdir(parents=True, exist_ok=True)

    report = {"date": datetime.now().isoformat(timespec="seconds"), "labelled_set": str(LABELLED.relative_to(ROOT))}
    report["keyword_fallback"] = score(rows, lambda r: fallback.classify_by_keywords(r["message"]).intent)
    print(f"Keyword fallback, all {len(rows)} tickets: accuracy {report['keyword_fallback']['accuracy']:.1%}, "
          f"unsafe misses {report['keyword_fallback']['unsafe_misses']}")

    if not args.fallback_only:
        s = get_settings()
        llm = get_llm()
        random.seed(args.seed)
        groups = defaultdict(list)
        for r in rows:
            groups[r["expected_intent"]].append(r)
        sample = [r for g in groups.values() for r in random.sample(g, min(args.per_intent, len(g)))]
        cost, latency, errors = 0.0, [], 0

        def predict(r):
            nonlocal cost, errors
            try:
                res = classifier.classify(llm, r["message"], s)
            except (LLMUnavailable, LLMOutputError) as e:
                errors += 1
                return f"ERROR: {e}"
            cost += res.cost_usd
            latency.append(res.latency_ms)
            return res.parsed.intent

        model_score = score(sample, predict)
        model_score.update(model=s.model_fast, prompt=classifier.PROMPT_VERSION, cost_usd=round(cost, 4),
                           avg_latency_ms=int(sum(latency) / max(1, len(latency))), errors=errors)
        report["model"] = model_score
        print(f"{s.model_fast} ({classifier.PROMPT_VERSION}), {len(sample)} tickets ({args.per_intent} per intent): "
              f"accuracy {model_score['accuracy']:.1%}, unsafe misses {model_score['unsafe_misses']}, "
              f"cost ${cost:.4f}, avg {model_score['avg_latency_ms']} ms")
        print("per intent:", model_score["per_intent"])
        for m in model_score["misses"]:
            print(f"  miss: {m['message']!r} expected {m['expected']} got {m['got']}")

    out = RESULTS / f"intent_eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("saved", out.relative_to(ROOT))


if __name__ == "__main__":
    main()

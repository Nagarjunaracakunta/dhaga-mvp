"""How often does the returns classifier pick the right reason? Compares the AI reasons saved in Supabase with
data/returns_eval/returns_labelled.csv (written by scripts/generate_return_comments.py). Free: no model calls.

    python evals/returns_eval.py

Run POST /api/returns/classify (or the "Classify with AI" button) first.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.modules.returns.classifier import needs_review  # noqa: E402
from backend.shared.db import get_supabase  # noqa: E402

LABELLED = ROOT / "data" / "returns_eval" / "returns_labelled.csv"


def main():
    labels = {r["return_id"]: r for r in csv.DictReader(LABELLED.open())}
    saved = {r["return_id"]: r for r in get_supabase().table("returns")
             .select("return_id,ai_category,ai_subcategory,ai_confidence").in_("return_id", list(labels)).execute().data}
    rows = [(labels[k], saved[k]) for k in labels if saved.get(k, {}).get("ai_category")]
    if not rows:
        sys.exit("No AI reasons saved yet: run the classifier first.")

    hits, sub_hits, area_hits, fit_n, per, misses = 0, 0, 0, 0, defaultdict(lambda: [0, 0]), []
    auto_wrong = 0  # wrong AND confident enough to skip review: the misses a person would not see
    for lab, ai in rows:
        sub, _, area = (ai["ai_subcategory"] or "NONE").partition(":")
        ok = ai["ai_category"] == lab["true_category"]
        hits += ok
        per[lab["true_category"]][0] += ok
        per[lab["true_category"]][1] += 1
        if lab["true_category"] == "FIT":
            fit_n += 1
            sub_hits += ok and sub == lab["true_sub_reason"]
            area_hits += ok and (area or "NONE") == lab["true_body_area"]
        if not ok:
            reviewed = needs_review(ai["ai_category"], ai["ai_confidence"])
            auto_wrong += not reviewed
            misses.append({"comment": lab["comment"], "expected": lab["true_category"], "got": ai["ai_category"],
                           "confidence": ai["ai_confidence"], "sent_to_review": reviewed})

    report = {
        "date": datetime.now().isoformat(timespec="seconds"), "n": len(rows),
        "category_accuracy": round(hits / len(rows), 4),
        "fit_detail_accuracy": {"sub_reason": f"{sub_hits}/{fit_n}", "body_area": f"{area_hits}/{fit_n}"},
        "per_category": {k: f"{v[0]}/{v[1]}" for k, v in sorted(per.items())},
        "wrong_and_not_sent_to_review": auto_wrong,
        "misses": misses,
    }
    print(f"{len(rows)} comments: category accuracy {report['category_accuracy']:.1%}; "
          f"FIT detail: sub-reason {sub_hits}/{fit_n}, body area {area_hits}/{fit_n}")
    print("per category:", report["per_category"])
    print(f"wrong but confident (not sent to review): {auto_wrong}")
    for m in misses:
        print(f"  miss: {m['comment']!r} expected {m['expected']} got {m['got']} ({m['confidence']}) "
              f"{'-> review' if m['sent_to_review'] else ''}")
    out = ROOT / "evals" / "results" / f"returns_eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

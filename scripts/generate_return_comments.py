"""Rewrite the "Other" return comments so they look like real customer text, with a known reason for each.

Why: the 216 "Other" returns in Supabase had 6 distinct comments. Only customer_comment changes (and any
saved AI results are cleared); ids, orders and reasons stay. The labels let us measure the classifier.

    python scripts/generate_return_comments.py            # writes data/returns_eval/returns_labelled.csv only
    python scripts/generate_return_comments.py --apply    # backs up current comments, then updates Supabase
    python scripts/generate_return_comments.py --restore  # puts the original comments back
"""
import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.shared.db import get_supabase  # noqa: E402

OUT_DIR = ROOT / "data" / "returns_eval"
LABELLED = OUT_DIR / "returns_labelled.csv"
BACKUP = OUT_DIR / "returns_comments_original.csv"
random.seed(20261004)

# (category, sub_reason, body_area): weight, templates. Neha (§05): most "Other" comments are about fit.
TEMPLATES = {
    ("FIT", "TOO_TIGHT", "SHOULDERS"): (16, ["shoulders pe bahut tight hai", "{size} size bhi shoulders se tight", "shoulder fitting is very tight, cannot lift arms",
                                             "kandhe pe fit nahi aaya, tight hai", "too snug at the shoulders"]),
    ("FIT", "TOO_TIGHT", "BUST"): (6, ["chest pe bahut tight hai", "bust area tight hai", "chhati ke paas tight lag raha"]),
    ("FIT", "TOO_TIGHT", "WAIST"): (6, ["kamar pe tight, button band nahi hua", "waist too tight even in {size}", "waist pe fit nahi hua"]),
    ("FIT", "TOO_TIGHT", "SLEEVES"): (4, ["sleeves bahut tight hai", "arms pe tight hai, sleeves chhoti fitting"]),
    ("FIT", "TOO_LOOSE", "OVERALL"): (5, ["bahut loose hai, size bada lag raha", "baggy fit, way too big", "poora dhila hai"]),
    ("FIT", "TOO_LOOSE", "WAIST"): (3, ["waist dhila hai", "loose at the waist"]),
    ("FIT", "TOO_SHORT", "LENGTH"): (4, ["length chhoti hai", "too short for me, I am 5'7", "kurta ki length kam hai"]),
    ("FIT", "TOO_LONG", "LENGTH"): (2, ["length zyada hai, floor pe lag raha", "too long, trails on the floor"]),
    ("COLOUR", "LISTING_DIFFERENCE", "NONE"): (14, ["rang bilkul alag hai photo se", "colour looks different from the app", "shade bahut dark hai, photo mein light tha",
                                                    "app pe bright dikha, asli mein faded", "colour photo jaisa nahi hai"]),
    ("QUALITY", "FABRIC", "NONE"): (12, ["fabric bahut patla hai", "kapda transparent hai", "material feels cheap", "kapda rough hai, chubh raha",
                                         "thinner than expected, see through"]),
    ("QUALITY", "STITCHING", "NONE"): (6, ["stitching nikal gayi pehli baar mein", "dhaage nikal rahe hain", "seam khul gaya after one wash"]),
    ("DAMAGE", "NONE", "NONE"): (4, ["daag tha kapde pe", "phata hua aaya", "button toota hua tha"]),
    ("WRONG_ITEM", "NONE", "NONE"): (4, ["galat size bheja, maine {other} order kiya tha", "different design aaya", "ye mera order nahi hai"]),
    ("CHANGED_MIND", "NONE", "NONE"): (8, ["ab zarurat nahi hai", "function cancel ho gaya", "galti se order ho gaya", "sasta mil gaya kahin aur"]),
    ("UNCLEAR", "NONE", "NONE"): (7, ["not good", "return karna hai", "ok", "bekaar", "nahi"]),
}
PREFIX = ["", "", "", "", "Hi, ", "sorry but ", "Mam ", "pls note "]
SUFFIX = ["", "", "", ".", "!!", " pls refund", " very disappointed", " 🙁", " return please"]
SIZES = ["S", "M", "L", "XL"]


def noisy(text: str) -> str:
    if random.random() < 0.2:
        text = text.lower()
    if random.random() < 0.15 and len(text) > 6:  # a typo: drop one letter
        i = random.randrange(1, len(text) - 1)
        text = text[:i] + text[i + 1:]
    return text


def make(key, size):
    text = random.choice(TEMPLATES[key][1]).format(size=size if size in SIZES else "M",
                                                   other=random.choice([s for s in SIZES if s != size]))
    return noisy(f"{random.choice(PREFIX)}{text}{random.choice(SUFFIX)}").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()
    sb = get_supabase()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.restore:
        rows = list(csv.DictReader(BACKUP.open()))
        for i in range(0, len(rows), 200):
            sb.table("returns").upsert(rows[i:i + 200], on_conflict="return_id").execute()
        print(f"restored {len(rows)} original comments")
        return

    rows = (sb.table("returns").select("return_id,order_item_id,customer_id,customer_comment,order_items(size)")
            .eq("original_reason", "Other").order("return_id").execute().data)
    keys, weights = list(TEMPLATES), [v[0] for v in TEMPLATES.values()]
    seen, labelled = set(), []
    for r in rows:
        key = random.choices(keys, weights=weights)[0]
        for _ in range(20):
            comment = make(key, (r.get("order_items") or {}).get("size"))
            if comment not in seen:
                break
        seen.add(comment)
        labelled.append({"return_id": r["return_id"], "order_item_id": r["order_item_id"], "customer_id": r["customer_id"],
                         "true_category": key[0], "true_sub_reason": key[1], "true_body_area": key[2],
                         "comment": comment, "original": r["customer_comment"]})

    with LABELLED.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["return_id", "true_category", "true_sub_reason", "true_body_area", "comment"])
        w.writeheader()
        w.writerows({k: r[k] for k in w.fieldnames} for r in labelled)
    print(f"{len(labelled)} Other returns, {len(seen)} distinct comments")
    print("mix:", dict(Counter(r["true_category"] for r in labelled).most_common()))
    print("examples:", [r["comment"] for r in random.sample(labelled, 8)])

    if args.apply:
        if not BACKUP.exists():
            with BACKUP.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["return_id", "order_item_id", "customer_id", "customer_comment"])
                w.writeheader()
                w.writerows({"return_id": r["return_id"], "order_item_id": r["order_item_id"],
                             "customer_id": r["customer_id"], "customer_comment": r["original"]} for r in labelled)
            print(f"backed up original comments to {BACKUP.relative_to(ROOT)}")
        update = [{"return_id": r["return_id"], "order_item_id": r["order_item_id"], "customer_id": r["customer_id"],
                   "customer_comment": r["comment"], "ai_category": None, "ai_subcategory": None,
                   "ai_confidence": None, "final_category": None} for r in labelled]
        for i in range(0, len(update), 200):
            sb.table("returns").upsert(update[i:i + 200], on_conflict="return_id").execute()
        print(f"updated {len(update)} comments in Supabase (saved AI results cleared)")


if __name__ == "__main__":
    main()

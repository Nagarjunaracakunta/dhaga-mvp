"""Generate realistic demo data for Dhaga (seeded, reproducible).

Writes to data/: products.csv, orders.csv, returns.csv, returns_ground_truth.csv
The ground-truth file is NOT used by the app; it exists so we can measure the LLM classifier later.
Planted patterns (what the pipeline should surface):
  - SKU4421 Floral Midi Dress, sizes M/L: shoulders too tight (fit)
  - SKU4450 Chikankari Top, Mustard: looks yellow/different online (colour)
  - SKU4435 Anarkali Suit: fabric quality complaints
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
DATA = Path(__file__).resolve().parent.parent / "data"

PRODUCTS = [
    # id, name, category, sizes, colours, weight (order share)
    ("SKU4421", "Floral Midi Dress", "Dresses", ["XS", "S", "M", "L", "XL"], ["Pink", "Blue", "Yellow"], 14),
    ("SKU4422", "Linen Kurta Set", "Kurta Sets", ["S", "M", "L", "XL"], ["White", "Green", "Blue"], 14),
    ("SKU4430", "Cotton Straight Kurta", "Kurtas", ["S", "M", "L", "XL", "XXL"], ["Red", "Black", "Mustard"], 18),
    ("SKU4435", "Anarkali Suit", "Suits", ["S", "M", "L", "XL"], ["Maroon", "Green", "Pink"], 10),
    ("SKU4440", "Palazzo Pants", "Bottoms", ["S", "M", "L", "XL"], ["Black", "White", "Blue"], 14),
    ("SKU4445", "Embroidered Dupatta", "Accessories", ["FREE"], ["Red", "Pink", "Green"], 8),
    ("SKU4450", "Chikankari Top", "Tops", ["S", "M", "L", "XL"], ["White", "Mustard", "Peach"], 12),
    ("SKU4455", "Denim Jacket", "Outerwear", ["S", "M", "L", "XL"], ["Blue", "Black"], 10),
]
P = {p[0]: p for p in PRODUCTS}

# (primary, sub, body_area) -> comment templates ({s}=size, {c1}/{c2}=listed/actual colour)
COMMENTS = {
    ("FIT", "TOO_TIGHT", "SHOULDERS"): [
        "{s} size shoulders pe bahut tight hai", "shoulder fitting is very tight, cannot lift arms",
        "kandhe pe fit nahi aa raha, tight hai", "Shoulders too snug even in {s}", "shoulders me bahut tight, hath utha nahi sakti"],
    ("FIT", "TOO_TIGHT", "WAIST"): ["waist bahut tight hai", "waist pe fit nahi hua, too tight", "kamar pe tight, button band nahi hua"],
    ("FIT", "TOO_TIGHT", "BUST"): ["bust area tight hai", "chest pe bahut tight fitting", "chhati ke paas tight lag raha hai"],
    ("FIT", "TOO_LOOSE", "WAIST"): ["waist loose hai, bahut dhila", "too loose at the waist", "kamar pe dhila hai"],
    ("FIT", "TOO_LOOSE", None): ["overall bahut loose hai", "size bada hai, baggy lag raha"],
    ("FIT", "TOO_SHORT", "LENGTH"): ["length bahut kam hai", "kurta ki length chhoti hai", "too short for me, 5'7"],
    ("FIT", "TOO_LONG", "LENGTH"): ["length zyada lambi hai", "too long, trails on floor"],
    ("QUALITY", "FABRIC", None): [
        "quality bilkul achhi nahi lagi, fabric cheap hai", "fabric thin hai, transparent dikh raha",
        "kapda bahut rough hai", "material feels cheap, not worth the price"],
    ("QUALITY", "STITCHING", None): ["stitching nikal gayi pehli baar mein", "threads loose hain, seam khul gaya", "stitching is poor"],
    ("COLOUR", "LISTING_DIFFERENCE", None): [
        "colour website pe {c1} tha but actual {c2} jaisa hai", "photo mein colour alag dikha",
        "rang bilkul alag hai, photo se match nahi", "colour looks different from the listing"],
    ("DAMAGE", "UNSPECIFIED", None): ["packet phata hua tha", "stain on the dress when it arrived", "buttons toote hue the"],
    ("WRONG_ITEM", "UNSPECIFIED", None): ["galat colour bhej diya", "received a different product", "mera order ye nahi tha"],
    ("CHANGED_MIND", "UNSPECIFIED", None): ["mann badal gaya", "bought for wedding, event cancelled", "don't need it anymore"],
    ("UNCLEAR", "UNCLEAR", None): ["not good", "nahi chahiye", "ok ok", ".", "see photo", "meh", "pasand nahi aaya", "return karna hai"],
}

DROPDOWN = {
    ("FIT", "TOO_TIGHT"): "Size too small", ("FIT", "TOO_LOOSE"): "Size too large",
    ("QUALITY", None): "Quality not as expected", ("COLOUR", None): "Colour different from photo",
    ("DAMAGE", None): "Damaged product", ("WRONG_ITEM", None): "Wrong item received",
    ("CHANGED_MIND", None): "Changed my mind",
}

SIZE_NOISE = {"S": ["small", "s "], "M": ["Medium", "m", "medium"], "L": ["Large", "l", " L"], "XL": ["xl", "Extra Large"]}
COLOUR_NOISE = {"Pink": ["pink", "PINK", "pinkish"], "Blue": ["navy blue", "BLUE"], "Black": ["black"], "White": ["off white"]}


def pick_reason(pid, size, colour):
    """Hidden true reason for a returned item; planted patterns are baked in here."""
    r = random.random()
    if pid == "SKU4421" and size in ("M", "L") and r < 0.6:
        return ("FIT", "TOO_TIGHT", "SHOULDERS")
    if pid == "SKU4450" and colour == "Mustard" and r < 0.6:
        return ("COLOUR", "LISTING_DIFFERENCE", None)
    if pid == "SKU4435" and r < 0.45:
        return ("QUALITY", random.choice(["FABRIC", "FABRIC", "STITCHING"]), None)
    return random.choices(
        [("FIT", "TOO_TIGHT", "WAIST"), ("FIT", "TOO_TIGHT", "BUST"), ("FIT", "TOO_LOOSE", "WAIST"),
         ("FIT", "TOO_LOOSE", None), ("FIT", "TOO_SHORT", "LENGTH"), ("FIT", "TOO_LONG", "LENGTH"),
         ("QUALITY", "FABRIC", None), ("QUALITY", "STITCHING", None), ("COLOUR", "LISTING_DIFFERENCE", None),
         ("DAMAGE", "UNSPECIFIED", None), ("WRONG_ITEM", "UNSPECIFIED", None),
         ("CHANGED_MIND", "UNSPECIFIED", None), ("UNCLEAR", "UNCLEAR", None)],
        weights=[8, 5, 6, 4, 6, 3, 8, 6, 8, 4, 3, 10, 6])[0]


def return_prob(pid, size, colour):
    if pid == "SKU4421" and size in ("M", "L"):
        return 0.38
    if pid == "SKU4450" and colour == "Mustard":
        return 0.33
    if pid == "SKU4435":
        return 0.24
    return 0.09


def main():
    DATA.mkdir(exist_ok=True)
    with open(DATA / "products.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["product_id", "product_name", "category"])
        for p in PRODUCTS:
            w.writerow(p[:3])

    start = date(2026, 7, 1)
    orders, returns, truth = [], [], []
    weights = [p[5] for p in PRODUCTS]
    for n in range(1, 3601):
        p = random.choices(PRODUCTS, weights=weights)[0]
        size, colour = random.choice(p[3]), random.choice(p[4])
        od = start + timedelta(days=random.randint(0, 84))
        oid = f"ORD{89000 + n}"
        orders.append([oid, f"C{1000 + random.randint(0, 1800)}", p[0], size, colour, od.isoformat()])

        if random.random() < return_prob(p[0], size, colour):
            prim, sub, body = pick_reason(p[0], size, colour)
            key_dd = (prim, sub if prim == "FIT" else None)
            dropdown = DROPDOWN.get(key_dd)
            # Fit issues with a body area / length and unclear reasons usually end up in "Other"
            if prim == "FIT" and (body or sub in ("TOO_SHORT", "TOO_LONG")) and random.random() < 0.6:
                dropdown = None
            elif prim == "FIT" and random.random() < 0.15:
                dropdown = None
            elif prim in ("QUALITY", "COLOUR") and random.random() < 0.2:
                dropdown = None
            elif prim == "UNCLEAR":
                dropdown = None
            reason = dropdown or "Other"
            comment = ""
            if reason == "Other":
                if random.random() < 0.9:
                    comment = random.choice(COMMENTS[(prim, sub, body)])
            elif random.random() < 0.05:
                comment = random.choice(COMMENTS[(prim, sub, body)])
            others = [c for c in p[4] if c != colour]
            comment = comment.format(s=size, c1=colour.lower(), c2=(random.choice(others) if others else "alag").lower())

            r_size, r_col = size, colour
            if random.random() < 0.06 and r_size in SIZE_NOISE:
                r_size = random.choice(SIZE_NOISE[r_size])
            if random.random() < 0.06 and r_col in COLOUR_NOISE:
                r_col = random.choice(COLOUR_NOISE[r_col])
            rd = od + timedelta(days=random.randint(3, 15))
            rid = f"R{len(returns) + 1:04d}"
            returns.append([rid, oid, orders[-1][1], p[0], p[1], p[2], r_size, r_col, reason, comment, rd.isoformat()])
            truth.append([rid, prim, sub, body or ""])

    # ---- deliberately dirty records (the pipeline must catch these, not crash) ----
    returns[5][3] = ""                          # missing product_id
    returns[17][10] = "31/09/2026"              # invalid date
    returns[29][10] = "2026-13-40"              # invalid date
    returns[41][1] = "ORD00000"                 # order not found
    returns[53][6] = "XXXL-ish"                 # unknown size
    returns[67][8] = "Refund asap"              # unknown dropdown value
    returns[80][3] = "SKU9999"                  # unknown product
    returns.append(list(returns[10]))           # duplicate return_id
    returns.append(list(returns[22])); returns[-1][0] = "R0999"; returns[-1][3] = "SKU4430"  # product != order's product
    orders.append(list(orders[3]))              # duplicate order_id

    for name, header, rows in [
        ("orders.csv", ["order_id", "customer_id", "product_id", "size", "colour", "order_date"], orders),
        ("returns.csv", ["return_id", "order_id", "customer_id", "product_id", "product_name", "category",
                         "size", "colour", "return_reason", "return_comment", "return_date"], returns),
        ("returns_ground_truth.csv", ["return_id", "true_primary", "true_sub", "true_body_area"], truth),
    ]:
        with open(DATA / name, "w", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"products={len(PRODUCTS)} orders={len(orders)} returns={len(returns)}")


if __name__ == "__main__":
    main()

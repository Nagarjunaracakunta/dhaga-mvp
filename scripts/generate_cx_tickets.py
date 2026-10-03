"""Rewrite support ticket messages so they look like real Dhaga & Co. support traffic, with a known intent for each.

Why: the synthetic tickets had 20 distinct messages across 1,800 rows. This keeps every ticket's id, customer
and order, and only replaces the message text. Each message fits its order (e.g. "delivered but not received"
only on delivered orders), and order numbers in the text are the ticket's real order.

    python scripts/generate_cx_tickets.py            # writes data/cx_eval/tickets_labelled.csv only
    python scripts/generate_cx_tickets.py --apply    # also backs up current messages and updates Supabase
    python scripts/generate_cx_tickets.py --restore  # puts the backed-up original messages back

Seeded, so the same input gives the same output.
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

OUT_DIR = ROOT / "data" / "cx_eval"
LABELLED = OUT_DIR / "tickets_labelled.csv"
BACKUP = OUT_DIR / "support_tickets_messages_original.csv"
random.seed(20261003)

# Intent mix per order status. Tuned so the overall mix lands near the brief's figure:
# 58% of tickets are "where is my order". The other shares are our estimate.
WEIGHTS = {
    "DELIVERED": {"WISMO": 30, "RETURN_REFUND": 25, "DAMAGED_OR_WRONG_ITEM": 18, "DELIVERED_NOT_RECEIVED": 10,
                  "COD_PAYMENT": 4, "OTHER": 13},
    "CANCELLED": {"WISMO": 20, "RETURN_REFUND": 60, "OTHER": 20},
    "NOT_DELIVERED": {"WISMO": 90, "CANCEL_ORDER": 5, "COD_PAYMENT": 3, "OTHER": 2},
}

ITEMS = ["kurti", "dress", "saree", "kurta set", "top", "palazzo", "dupatta", "frock", "shirt", "lehenga"]

TEMPLATES = {
    "WISMO": [
        "where is my order {ord}", "Mera order kaha hai {ord}", "order abhi tak nahi aaya", "kab tak aayega mera {item}?",
        "Kab tak delivery hoga", "my {item} was supposed to come {when}, still not here", "tracking not updating since {n} days",
        "{ord} ka status kya hai", "parcel kahan atka hua hai?", "delivery date nikal gayi, abhi tak kuch nahi aaya",
        "Order status please {ord}", "when will my order reach? need it for {occasion}", "courier wala phone nahi utha raha",
        "Shipped dikha raha hai {n} din se, aage kuch update nahi", "mujhe {occasion} ke liye chahiye tha, kab milega",
        "out for delivery tha kal, aaj tak nahi aaya", "can you check my order {ord}? no update", "order kidhar hai bhai",
        "It's been {n} days since I ordered. Where is it?", "tracking link kaam nahi kar raha, order kab aayega",
        "pls tell me delivery date for {ord}", "order mila nahi abhi tak, kya hua?", "status check karo please {ord}",
    ],
    "DELIVERED_NOT_RECEIVED": [
        "App shows delivered but I never received the parcel", "delivered dikha raha hai par mujhe mila nahi",
        "order {ord} marked delivered, nobody came to my house", "parcel deliver hua bol raha hai lekin aaya hi nahi",
        "I didn't get my {item} but status says delivered", "watchman ne bhi nahi liya, phir delivered kaise dikha raha",
        "delivered status galat hai, maine kuch receive nahi kiya {ord}", "it says delivered yesterday but I got nothing",
    ],
    "DAMAGED_OR_WRONG_ITEM": [
        "I received a damaged {item}", "packet phata hua tha aur {item} pe daag hai", "galat colour bhej diya aapne",
        "wrong size aaya hai, maine {size} order kiya tha", "stitching khul gayi pehli baar pehente hi",
        "received a different product, not what i ordered {ord}", "{item} torn hai, very bad quality",
        "colour completely different, mustard ki jagah yellow aaya", "button toote hue the {item} mein",
        "stain on the {item} when it arrived, pls replace", "wrong item delivered, ye mera order nahi hai",
    ],
    "RETURN_REFUND": [
        "How can I get a refund?", "{item} fit nahi hua, return karna hai", "return kaise karu {ord}",
        "refund kab aayega? pickup ho gaya {n} din pehle", "size chhota hai, exchange ya return chahiye",
        "I want to return my {item}, didn't like the fabric", "return request kaise daalun app mein",
        "refund status for {ord} please", "pickup boy aaya hi nahi return ke liye", "paise wapas kab milenge",
        "shoulders se bahut tight hai, return please", "not happy with the {item}, need refund",
    ],
    "CANCEL_ORDER": [
        "Cancel kar do please, ab nahi chahiye", "please cancel my order {ord}", "order cancel karna hai",
        "I ordered by mistake, cancel it", "cancel {ord}, found it cheaper elsewhere", "galti se 2 baar order ho gaya, ek cancel karo",
        "mujhe ye order nahi chahiye, cancel kardo", "how to cancel order? option nahi dikh raha",
    ],
    "COD_PAYMENT": [
        "I need help with COD", "COD pe UPI se pay kar sakte hai?", "cash on delivery available hai kya {ord}",
        "delivery boy change nahi de raha, kya karu", "can i pay by gpay at delivery?", "COD charges kyun lag rahe hai",
        "online pay kiya tha phir bhi COD maang rahe", "COD amount kitna dena hai {ord}",
    ],
    "OTHER": [
        "I was charged twice", "ok ok", "hi", "thanks", "do you have this {item} in XXL?", "app crash ho raha hai",
        "coupon code kaam nahi kar raha", "address change karna hai", "aapka store kahan hai?", "invoice chahiye GST wala",
        "new collection kab aayega", "size chart sahi hai kya?",
    ],
}
PREFIX = ["", "", "", "Hi, ", "Hello team, ", "Sir/Mam ", "Hii ", "Namaste, ", "Dhaga team, ", "Excuse me "]
SUFFIX = ["", "", "", ".", "?", " pls reply", " urgent!!", " very bad service", " 🙏", " plz help", " asap",
          " please check", " third time messaging", " :("]
WHEN = ["yesterday", "on Monday", "last week", "3 days back", "by Friday"]
OCCASIONS = ["mehndi", "office", "Diwali", "shaadi", "puja", "college fest"]
SIZES = ["S", "M", "L", "XL"]


def noisy(text: str) -> str:
    r = random.random()
    if r < 0.15:
        text = text.lower()
    elif r < 0.20:
        text = text.upper()
    if random.random() < 0.15:  # a typo: drop one letter
        i = random.randrange(1, max(2, len(text) - 1))
        text = text[:i] + text[i + 1:]
    if random.random() < 0.1:
        text = text.replace("please", "plz").replace("Please", "Plz")
    return text


def make_message(intent: str, order_number: str) -> str:
    tpl = random.choice(TEMPLATES[intent])
    ordref = random.choice([order_number, f"#{order_number}", order_number.lower(), f"order no {order_number}",
                            f"order id {order_number}"])
    body = tpl.format(ord=ordref if random.random() < 0.7 else "", item=random.choice(ITEMS), n=random.randint(2, 12),
                      when=random.choice(WHEN), occasion=random.choice(OCCASIONS), size=random.choice(SIZES))
    if "{ord}" not in tpl and intent not in ("OTHER",) and random.random() < 0.2:
        body += f" ({ordref})"
    body = " ".join(body.split())
    return noisy(f"{random.choice(PREFIX)}{body}{random.choice(SUFFIX)}").strip()


def pick_intent(status: str) -> str:
    weights = WEIGHTS.get(status, WEIGHTS["NOT_DELIVERED"])
    return random.choices(list(weights), weights=list(weights.values()))[0]


def load_tickets(sb):
    rows, start = [], 0
    while True:
        batch = (sb.table("support_tickets")
                 .select("ticket_id,ticket_number,customer_id,message,orders(order_number,order_status)")
                 .order("ticket_number").range(start, start + 999).execute().data)
        rows += batch
        if len(batch) < 1000:
            return rows
        start += 1000


def upsert(sb, rows):
    for i in range(0, len(rows), 500):
        sb.table("support_tickets").upsert(rows[i:i + 500], on_conflict="ticket_id").execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="update support_tickets.message in Supabase")
    ap.add_argument("--restore", action="store_true", help="restore the original messages from the backup")
    args = ap.parse_args()
    sb = get_supabase()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.restore:
        with BACKUP.open() as f:
            rows = [{"ticket_id": r["ticket_id"], "ticket_number": r["ticket_number"], "customer_id": r["customer_id"],
                     "message": r["message"]} for r in csv.DictReader(f)]
        upsert(sb, rows)
        print(f"restored {len(rows)} original messages")
        return

    tickets = load_tickets(sb)
    seen, labelled = set(), []
    for t in tickets:
        order = t.get("orders") or {}
        status, number = order.get("order_status", "IN_TRANSIT"), order.get("order_number", "")
        intent = pick_intent(status)
        for _ in range(20):  # keep messages unique
            msg = make_message(intent, number)
            if msg not in seen:
                break
        seen.add(msg)
        labelled.append({"ticket_id": t["ticket_id"], "ticket_number": t["ticket_number"], "customer_id": t["customer_id"],
                         "order_status": status, "expected_intent": intent, "message": msg, "original": t["message"]})

    with LABELLED.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticket_number", "order_status", "expected_intent", "message"])
        w.writeheader()
        w.writerows({k: r[k] for k in w.fieldnames} for r in labelled)
    print(f"{len(labelled)} tickets, {len(seen)} distinct messages")
    print("intent mix:", dict(Counter(r["expected_intent"] for r in labelled).most_common()))
    print("examples:", [r["message"] for r in random.sample(labelled, 8)])

    if args.apply:
        if not BACKUP.exists():  # never overwrite the first backup
            with BACKUP.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ticket_id", "ticket_number", "customer_id", "message"])
                w.writeheader()
                w.writerows({"ticket_id": r["ticket_id"], "ticket_number": r["ticket_number"],
                             "customer_id": r["customer_id"], "message": r["original"]} for r in labelled)
            print(f"backed up original messages to {BACKUP.relative_to(ROOT)}")
        upsert(sb, [{"ticket_id": r["ticket_id"], "ticket_number": r["ticket_number"], "customer_id": r["customer_id"],
                     "message": r["message"]} for r in labelled])
        print(f"updated {len(labelled)} messages in Supabase")


if __name__ == "__main__":
    main()

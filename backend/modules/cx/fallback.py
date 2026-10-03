"""Used when Claude is unavailable: keyword intent detection and the canned replies agents already use.

Templates only state order facts and point to next steps. Review them against the real policies before go-live.
"""
import re
from typing import Optional

from .schemas import OrderFacts, TicketClassification

ORDER_NO = re.compile(r"\bDHC\d+\b", re.I)

# Checked in order; first match wins
KEYWORDS = [
    ("DELIVERED_NOT_RECEIVED", [r"delivered.*(not|never|nahi|nhi).*(receiv|got|mila)", r"(not|never|nahi|nhi).*(receiv|mila).*delivered"]),
    ("DAMAGED_OR_WRONG_ITEM", [r"damag", r"torn", r"phat", r"defect", r"stain", r"wrong (item|product|size|colou?r)",
                               r"galat", r"different product", r"not what i ordered"]),
    ("CANCEL_ORDER", [r"cancel"]),
    ("RETURN_REFUND", [r"refund", r"return", r"wapas", r"exchange"]),
    ("COD_PAYMENT", [r"\bcod\b", r"cash", r"\bupi\b", r"\bpay\b", r"payment"]),
    ("WISMO", [r"where", r"\bkab\b", r"\bkaha", r"status", r"\blate\b", r"track", r"nahi aaya", r"nhi aaya", r"deliver", r"kab tak", r"pahunch"]),
]
STATUS_TEXT = {
    "CONFIRMED": "confirmed and being packed",
    "SHIPPED": "shipped",
    "IN_TRANSIT": "on its way",
    "OUT_FOR_DELIVERY": "out for delivery today",
    "DELIVERED": "delivered",
    "CANCELLED": "cancelled",
    "RTO_INITIATED": "being returned to us",
}
HINDI_HINTS = re.compile(r"\b(hai|nahi|nhi|kab|kya|mera|mujhe|kar|aaya|chahiye|kyun|abhi)\b", re.I)


def classify_by_keywords(message: str) -> TicketClassification:
    text = message.lower()
    order = ORDER_NO.search(message)
    language = "hinglish" if HINDI_HINTS.search(message) else "english"
    for intent, patterns in KEYWORDS:
        if any(re.search(p, text) for p in patterns):
            return TicketClassification(intent=intent, confidence=0.75, language=language,
                                        order_number=order.group(0).upper() if order else None)
    return TicketClassification(intent="OTHER", confidence=0.3, language=language,
                                order_number=order.group(0).upper() if order else None)


def _day(d) -> str:
    return f"{d.day} {d.strftime('%B')}"


def _amount(x: Optional[float]) -> str:
    return f"₹{x:,.0f}" if x is not None else "the order amount"


def needs_info_reply(first_name: str) -> str:
    return (f"Hi {first_name}, happy to check this for you. Could you share your order number? "
            "It starts with DHC and is in your order confirmation message.\n\nTeam Dhaga")


def template_reply(intent: str, facts: OrderFacts, first_name: str) -> str:
    num, status = facts.order_number, STATUS_TEXT.get(facts.status, facts.status.lower().replace("_", " "))
    if intent == "CANCEL_ORDER":
        body = (f"your order {num} has not been dispatched yet, so it can be cancelled. A teammate will confirm the cancellation shortly."
                if facts.is_cancellable else
                f"your order {num} is already {status}, so it can't be cancelled now. A teammate will share your options.")
    elif intent == "RETURN_REFUND":
        body = (f"to return an item from order {num}, open the Dhaga app, go to Orders, choose this order and tap Return. "
                "A teammate will help if you have any trouble.")
    elif intent == "COD_PAYMENT":
        body = f"your order {num} is {status}. The amount due on delivery is {_amount(facts.total_amount)}. A teammate will confirm the payment options."
    elif facts.is_delivered and facts.delivered_on:
        body = f"our records show order {num} was delivered on {_day(facts.delivered_on)}."
    else:
        body = f"your order {num} is {status}"
        body += f" with {facts.courier}" if facts.courier else ""
        body += f", expected by {_day(facts.expected_delivery)}." if facts.expected_delivery and not facts.days_late else "."
        if facts.days_late:
            body = f"sorry for the delay. {body[0].upper()}{body[1:]} It is {facts.days_late} days past the expected date, and a teammate will follow up with the courier."
        if facts.tracking_number:
            body += f" Tracking number: {facts.tracking_number}."
    return f"Hi {first_name}, {body}\n\nTeam Dhaga"

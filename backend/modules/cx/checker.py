"""Check a draft before an agent sees it.

code_check: every order number, tracking number, amount and date in the reply must appear in the facts.
model_check: model call 3 (Haiku 4.5, temperature 0) judges whether it answers the question and follows policy.
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from backend.shared.llm import LLM, LLMResult
from backend.shared.settings import Settings

from .repository import Policy
from .schemas import DraftCheck, OrderFacts

PROMPT_VERSION = "check_v1"
SYSTEM = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text()

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}", re.I)
MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
ORDER_NO = re.compile(r"\bDHC\d+\b", re.I)
TRACKING_NO = re.compile(r"\b[A-Z]{3}\d{6,}\b")
AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)", re.I)


def _dates_in(text: str) -> set[tuple[int, int]]:
    found = {(int(d), MONTHS[m[:3].lower()]) for d, m in DAY_MONTH.findall(text)}
    found |= {(int(d), MONTHS[m[:3].lower()]) for m, d in MONTH_DAY.findall(text)}
    found |= {(int(d), int(m)) for _, m, d in ISO_DATE.findall(text)}
    return found


def code_check(reply: str, facts: Optional[OrderFacts]) -> list[str]:
    issues = []
    known_order = facts.order_number.upper() if facts else None
    for num in {n.upper() for n in ORDER_NO.findall(reply)}:
        if num != known_order:
            issues.append(f"Mentions order {num}, which is not this customer's order.")

    for code in set(TRACKING_NO.findall(reply)):
        if code.startswith("DHC"):
            continue
        if not facts or code != facts.tracking_number:
            issues.append(f"Mentions tracking number {code}, which is not in the order facts.")

    allowed_amounts = {round(facts.total_amount, 2)} if facts and facts.total_amount is not None else set()
    for raw in AMOUNT.findall(reply):
        value = round(float(raw.replace(",", "")), 2)
        if value not in allowed_amounts:
            issues.append(f"Mentions amount ₹{raw}, which does not match the order total.")

    known_dates: set[tuple[int, int]] = set()
    if facts:
        for d in [facts.expected_delivery, facts.delivered_on, facts.order_date]:
            if isinstance(d, date):
                known_dates.add((d.day, d.month))
    for day, month in _dates_in(reply):
        if (day, month) not in known_dates:
            issues.append(f"Mentions the date {day}/{month}, which is not in the order facts.")
    return issues


def model_check(llm: LLM, settings: Settings, *, message: str, reply: str, facts: OrderFacts,
                policy: Optional[Policy], today: Optional[date] = None) -> LLMResult[DraftCheck]:
    user = "\n\n".join([
        # Without today's date the reviewer judged past dates against its own idea of "now"
        f"<today>{(today or date.today()).isoformat()}</today>",
        f"<customer_message>\n{message}\n</customer_message>",
        f"<order_facts>\n{json.dumps(facts.model_dump(mode='json'), indent=2)}\n</order_facts>",
        f"<policy>\n{policy.text if policy else 'No policy document available.'}\n</policy>",
        f"<draft_reply>\n{reply}\n</draft_reply>",
    ])
    return llm.parse(model=settings.model_fast, system=SYSTEM, user=user, output_format=DraftCheck,
                     max_tokens=512, temperature=0)

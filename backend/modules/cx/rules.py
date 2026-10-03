"""Business rules that decide whether Copilot may draft a reply. Pure functions, no I/O."""
from typing import Optional

from .schemas import OrderFacts, RuleDecision, TicketClassification

TIER_2 = "Tier 2"


def decide(classification: TicketClassification, facts: Optional[OrderFacts], order_mismatch: bool,
           min_confidence: float, delay_priority_days: int) -> RuleDecision:
    """Checked in order; the first rule that matches wins."""
    intent = classification.intent

    if intent == "OTHER" or classification.confidence < min_confidence:
        return RuleDecision(action="NEEDS_HUMAN",
                            reason=f"Not sure what the customer is asking (confidence {classification.confidence:.0%}).")
    if order_mismatch:
        return RuleDecision(action="NEEDS_HUMAN",
                            reason="The order number in the message belongs to a different customer.")
    if facts is None:
        return RuleDecision(action="NEEDS_INFO",
                            reason="No order is linked to this ticket and none could be found for this customer.")
    if facts.status == "RTO_INITIATED":
        return RuleDecision(action="NEEDS_HUMAN", escalation_tier=TIER_2,
                            reason="Order is returning to origin. Follow the COD & RTO SOP before replying.")
    if intent == "DAMAGED_OR_WRONG_ITEM":
        return RuleDecision(action="NEEDS_HUMAN", escalation_tier=TIER_2,
                            reason="Damaged or wrong item. Tier 2 must check the customer's photos and arrange a replacement or return.")
    if intent == "DELIVERED_NOT_RECEIVED":
        return RuleDecision(action="NEEDS_HUMAN", escalation_tier=TIER_2,
                            reason="Possible lost parcel. A person must raise a courier claim before replying.")

    priority = None
    if facts.days_late is not None and facts.days_late > delay_priority_days:
        priority = f"Delayed {facts.days_late} days. Consider raising it with {facts.courier or 'the courier'}."
    return RuleDecision(action="DRAFT", priority_note=priority)

from datetime import date

from backend.modules.cx import checker, fallback, rules
from backend.modules.cx.order_facts import build_facts
from backend.modules.cx.schemas import TicketClassification

TODAY = date(2026, 10, 3)


def facts_for(repo, order_number):
    return build_facts(repo.find_order(order_number), TODAY, return_window_days=7)


def cls(intent="WISMO", confidence=0.95, order_number=None):
    return TicketClassification(intent=intent, confidence=confidence, order_number=order_number, language="english")


def decide(c, facts, mismatch=False):
    return rules.decide(c, facts, mismatch, min_confidence=0.7, delay_priority_days=5)


# ---------- order facts ----------
def test_late_order_counts_days_late(repo):
    f = facts_for(repo, "DHC100231")          # expected 27 Sep, still in transit on 3 Oct
    assert f.days_late == 6 and not f.is_delivered and not f.is_cancellable


def test_on_time_order_is_not_late(repo):
    assert facts_for(repo, "DHC100560").days_late is None


def test_delivered_order_return_window(repo):
    f = facts_for(repo, "DHC100377")          # delivered 30 Sep
    assert f.is_delivered and f.days_since_delivery == 3 and f.within_return_window is True


def test_only_confirmed_orders_are_cancellable(repo):
    assert facts_for(repo, "DHC100902").is_cancellable
    assert not facts_for(repo, "DHC100415").is_cancellable


def test_items_include_size_and_colour(repo):
    assert facts_for(repo, "DHC100377").items == ["Floral Midi Dress (M, Pink)"]


# ---------- rules ----------
def test_low_confidence_goes_to_a_person(repo):
    d = decide(cls(confidence=0.4), facts_for(repo, "DHC100560"))
    assert d.action == "NEEDS_HUMAN" and "40%" in d.reason


def test_other_intent_goes_to_a_person(repo):
    assert decide(cls(intent="OTHER"), facts_for(repo, "DHC100560")).action == "NEEDS_HUMAN"


def test_missing_order_asks_for_info():
    assert decide(cls(), None).action == "NEEDS_INFO"


def test_someone_elses_order_goes_to_a_person():
    assert decide(cls(), None, mismatch=True).action == "NEEDS_HUMAN"


def test_rto_and_not_received_escalate_to_tier_2(repo):
    assert decide(cls(), facts_for(repo, "DHC100611")).escalation_tier == "Tier 2"
    d = decide(cls(intent="DELIVERED_NOT_RECEIVED"), facts_for(repo, "DHC100318"))
    assert d.action == "NEEDS_HUMAN" and d.escalation_tier == "Tier 2"


def test_damaged_or_wrong_item_escalates_to_tier_2(repo):
    d = decide(cls(intent="DAMAGED_OR_WRONG_ITEM"), facts_for(repo, "DHC100377"))
    assert d.action == "NEEDS_HUMAN" and d.escalation_tier == "Tier 2"


def test_badly_late_order_is_drafted_with_priority(repo):
    d = decide(cls(), facts_for(repo, "DHC100231"))
    assert d.action == "DRAFT" and "6 days" in d.priority_note


# ---------- code check ----------
def test_code_check_passes_correct_reply(repo):
    f = facts_for(repo, "DHC100560")
    reply = "Hi Priya, order DHC100560 is with Delhivery (DEL100560), expected 4 October. Pay ₹1,436 on delivery."
    assert checker.code_check(reply, f) == []


def test_code_check_catches_invented_facts(repo):
    f = facts_for(repo, "DHC100560")
    reply = "Order DHC100999 will arrive on 6 Oct. Tracking EKA123456. Refund of Rs 500."
    issues = " ".join(checker.code_check(reply, f))
    assert "DHC100999" in issues and "6/10" in issues and "EKA123456" in issues and "500" in issues


def test_code_check_reads_month_first_and_iso_dates(repo):
    f = facts_for(repo, "DHC100560")
    assert checker.code_check("Expected October 4.", f) == []
    assert checker.code_check("Expected 2026-10-04.", f) == []
    assert checker.code_check("Expected October 9.", f)


# ---------- fallback ----------
def test_keyword_classifier_handles_hinglish():
    assert fallback.classify_by_keywords("Mera order abhi tak nahi aaya. Kab milega?").intent == "WISMO"
    assert fallback.classify_by_keywords("Cancel kar do please").intent == "CANCEL_ORDER"
    assert fallback.classify_by_keywords("shows delivered but I never received it").intent == "DELIVERED_NOT_RECEIVED"
    assert fallback.classify_by_keywords("I received a damaged product.").intent == "DAMAGED_OR_WRONG_ITEM"
    assert fallback.classify_by_keywords("galat colour bhej diya").intent == "DAMAGED_OR_WRONG_ITEM"
    c = fallback.classify_by_keywords("ok ok")
    assert c.intent == "OTHER" and c.confidence < 0.7


def test_keyword_classifier_extracts_order_number():
    assert fallback.classify_by_keywords("where is dhc100231?").order_number == "DHC100231"


def test_templates_pass_the_code_check(repo):
    for number, intent in [("DHC100560", "WISMO"), ("DHC100231", "WISMO"), ("DHC100902", "CANCEL_ORDER"),
                           ("DHC100377", "RETURN_REFUND"), ("DHC100488", "COD_PAYMENT")]:
        f = facts_for(repo, number)
        reply = fallback.template_reply(intent, f, "Priya")
        assert number in reply and checker.code_check(reply, f) == [], (number, reply)

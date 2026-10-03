"""The full workflow with a fake model: free, fast and repeatable."""
from backend.modules.cx import service
from backend.modules.cx.schemas import DraftCheck, DraftReply, TicketClassification
from backend.shared.llm import LLMOutputError, LLMUnavailable

from .conftest import FakeLLM, make_deps

WISMO = TicketClassification(intent="WISMO", confidence=0.95, order_number=None, language="hinglish")
GOOD_DRAFT = DraftReply(reply="Hi Priya, aapka order DHC100560 Delhivery ke saath hai, 4 October tak aa jayega.\n\nTeam Dhaga",
                        facts_used=["status", "courier", "expected_delivery"])
PASS = DraftCheck(passed=True, issues=[])


def test_happy_path_drafts_checks_and_logs(repo, settings):
    llm = FakeLLM(classify=WISMO, draft=GOOD_DRAFT, check=PASS)
    deps = make_deps(repo, settings, llm)
    r = service.analyze_ticket(deps, "TKT200001")

    assert r.status == "DRAFTED" and r.check.passed and r.draft == GOOD_DRAFT.reply
    assert r.facts.order_number == "DHC100560" and r.policy_used.startswith("Delivery FAQ")
    assert not r.fallback_mode and r.attempts == 1
    assert [c["schema"] for c in llm.calls] == ["TicketClassification", "DraftReply", "DraftCheck"]
    # model settings: Haiku at temperature 0 for classify/check, Opus at low effort for the draft
    assert llm.calls[0]["model"] == "claude-haiku-4-5" and llm.calls[0]["temperature"] == 0
    assert llm.calls[1]["model"] == "claude-opus-5-5" and llm.calls[1]["effort"] == "low"
    assert repo.get_ticket("TKT200001").status == "DRAFTED"
    logged = repo.get_interaction(r.interaction_id)
    assert logged["evaluation_status"] == "PASSED" and logged["input_reference_id"] == r.ticket_id


def test_invented_date_triggers_one_redraft(repo, settings):
    drafts = iter([
        DraftReply(reply="Hi Priya, order DHC100560 aa jayega 9 October tak.", facts_used=[]),
        GOOD_DRAFT,
    ])
    llm = FakeLLM(classify=WISMO, draft=lambda _: next(drafts), check=PASS)
    r = service.analyze_ticket(make_deps(repo, settings, llm), "TKT200001")
    assert r.status == "DRAFTED" and r.attempts == 2
    redraft_prompt = [c for c in llm.calls if c["schema"] == "DraftReply"][1]["user"]
    assert "previous_draft_issues" in redraft_prompt and "9/10" in redraft_prompt


def test_two_failed_checks_hand_over_to_a_person(repo, settings):
    llm = FakeLLM(classify=WISMO, draft=GOOD_DRAFT, check=DraftCheck(passed=False, issues=["Too vague"]))
    r = service.analyze_ticket(make_deps(repo, settings, llm), "TKT200001")
    assert r.status == "NEEDS_HUMAN" and r.attempts == 2 and r.draft and "twice" in r.human_reason
    assert repo.get_interaction(r.interaction_id)["evaluation_status"] == "FAILED"


def test_order_number_in_message_is_preferred(repo, settings):
    c = TicketClassification(intent="WISMO", confidence=0.95, order_number="DHC100231", language="hinglish")
    r = service.analyze_ticket(make_deps(repo, settings, FakeLLM(classify=c, draft=lambda _: DraftReply(
        reply="Hi Rahul, order DHC100231 is late.", facts_used=[]), check=PASS)), "TKT200014")
    assert r.facts.order_number == "DHC100231" and r.priority_note and "6 days" in r.priority_note


def test_someone_elses_order_is_not_shown(repo, settings):
    c = TicketClassification(intent="WISMO", confidence=0.95, order_number="DHC100560", language="english")
    r = service.analyze_ticket(make_deps(repo, settings, FakeLLM(classify=c)), "TKT200095")
    assert r.status == "NEEDS_HUMAN" and r.facts is None and "different customer" in r.human_reason


def test_refusal_or_bad_output_goes_to_a_person(repo, settings):
    llm = FakeLLM(classify=WISMO, draft=LLMOutputError("model declined to answer"))
    r = service.analyze_ticket(make_deps(repo, settings, llm), "TKT200001")
    assert r.status == "NEEDS_HUMAN" and r.draft is None and "declined" in r.human_reason


def test_model_outage_mid_run_switches_to_templates(repo, settings):
    llm = FakeLLM(classify=WISMO, draft=LLMUnavailable("Claude API rate limit reached"))
    r = service.analyze_ticket(make_deps(repo, settings, llm), "TKT200001")
    assert r.fallback_mode and r.status == "DRAFTED" and "DHC100560" in r.draft
    assert any("rate limit" in n for n in r.notes)


def test_no_api_key_runs_every_demo_ticket_in_fallback_mode(repo, settings):
    deps = make_deps(repo, settings)
    expected = {
        "TKT200001": "DRAFTED", "TKT200014": "DRAFTED", "TKT200027": "NEEDS_HUMAN", "TKT200033": "DRAFTED",
        "TKT200041": "NEEDS_HUMAN", "TKT200052": "DRAFTED", "TKT200060": "NEEDS_INFO", "TKT200071": "DRAFTED",
        "TKT200083": "NEEDS_HUMAN", "TKT200095": "NEEDS_HUMAN",
    }
    got = {t: service.analyze_ticket(deps, t).status for t in expected}
    assert got == expected

"""Bulk drafting for repeated questions: only confident, checked model drafts reach the group-review queue."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.cx import service
from backend.modules.cx.schemas import DraftCheck, DraftReply, TicketClassification

from .conftest import FakeLLM, make_deps


def _llm(confidence):
    return FakeLLM(
        classify=lambda user: TicketClassification(intent="WISMO", confidence=confidence, order_number=None,
                                                   language="english"),
        draft=DraftReply(reply="Hi, your order is on its way. Team Dhaga", facts_used=["status"]),
        check=DraftCheck(passed=True, issues=[]),
    )


def _client(repo, settings, llm):
    deps = make_deps(repo, settings, llm)
    app.dependency_overrides[service.get_deps] = lambda: deps
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def test_confident_drafts_are_grouped_and_can_be_approved_together(repo, settings):
    client = _client(repo, settings, _llm(0.92))
    run = client.post("/api/cx/bulk/draft", json={"limit": 3}).json()
    assert run["analysed"] == 3 and run["failed"] == 0
    assert run["ready"] + run["needs_person"] + run["below_threshold"] == 3

    q = client.get("/api/cx/bulk/queue").json()
    assert q["min_confidence"] == 0.75
    items = [i for g in q["groups"] for i in g["items"]]
    assert len(items) == run["ready"] and all(i["confidence"] >= 0.75 for i in items)
    if not items:
        pytest.skip("demo tickets all routed to a person")
    assert q["groups"][0]["intent"] == "WISMO"

    body = {"items": [{"ticket_ref": i["ticket_number"], "interaction_id": i["interaction_id"]} for i in items]}
    res = client.post("/api/cx/bulk/approve", json=body).json()
    assert res["approved"] == len(items)
    assert client.get("/api/cx/bulk/queue").json()["groups"] == []
    again = client.post("/api/cx/bulk/approve", json=body).json()
    assert again["approved"] == 0 and again["results"][0]["error"]


def test_drafts_below_the_bulk_threshold_stay_out_of_the_queue(repo, settings):
    client = _client(repo, settings, _llm(0.72))  # above the 0.70 rule, below the 0.75 bulk threshold
    run = client.post("/api/cx/bulk/draft", json={"limit": 3}).json()
    assert run["ready"] == 0
    assert client.get("/api/cx/bulk/queue").json()["groups"] == []


def test_fallback_drafts_are_never_bulk_approved(repo, settings):
    client = _client(repo, settings, None)  # no API key: keyword fallback, confidence 0.75
    client.post("/api/cx/bulk/draft", json={"limit": 3})
    assert client.get("/api/cx/bulk/queue").json()["groups"] == []


def test_batch_size_is_capped(repo, settings):
    client = _client(repo, settings, _llm(0.9))
    r = client.post("/api/cx/bulk/draft", json={"limit": 21})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BULK_LIMIT"


def test_a_second_run_skips_tickets_already_analysed(repo, settings):
    client = _client(repo, settings, _llm(0.9))
    ran = lambda: [r["input_reference_id"] for r in repo.interactions.values()]
    client.post("/api/cx/bulk/draft", json={"limit": 3})
    first = ran()
    client.post("/api/cx/bulk/draft", json={"limit": 3})
    second = ran()[len(first):]
    assert len(first) == 3 and len(second) == 3 and not set(first) & set(second)

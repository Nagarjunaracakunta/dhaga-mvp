"""Inbox: views, search and priority work over every ticket; tickets handed to a person get their own view."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.cx import service

from .conftest import make_deps


@pytest.fixture
def client(repo, settings):
    deps = make_deps(repo, settings)
    app.dependency_overrides[service.get_deps] = lambda: deps
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_counts_cover_every_ticket(client, repo):
    page = client.get("/api/cx/inbox", params={"limit": 2}).json()
    assert page["total"] == len(repo.tickets) == page["counts"]["all"]
    assert len(page["items"]) == 2


def test_handed_to_a_person_has_its_own_view(client):
    r = client.post("/api/cx/tickets/TKT200027/analyze").json()
    assert r["status"] == "NEEDS_HUMAN"
    page = client.get("/api/cx/inbox", params={"view": "needs_person"}).json()
    assert [i["ticket_number"] for i in page["items"]] == ["TKT200027"] and page["items"][0]["needs_person"]
    open_view = client.get("/api/cx/inbox", params={"view": "open", "limit": 200}).json()
    assert "TKT200027" not in [i["ticket_number"] for i in open_view["items"]]

    client.post("/api/cx/tickets/TKT200027/decision", json={"interaction_id": r["interaction_id"], "action": "ESCALATED"})
    assert client.get("/api/cx/inbox", params={"view": "needs_person"}).json()["total"] == 0


def test_search_matches_name_message_ticket_and_order(client):
    assert [i["ticket_number"] for i in client.get("/api/cx/inbox", params={"q": "tkt200001"}).json()["items"]] == ["TKT200001"]
    assert client.get("/api/cx/inbox", params={"q": "DHC100560"}).json()["total"] >= 1
    assert client.get("/api/cx/inbox", params={"q": "no such words anywhere"}).json()["total"] == 0


def test_priority_puts_late_orders_first(client):
    items = client.get("/api/cx/inbox", params={"sort": "priority", "view": "open", "limit": 200}).json()["items"]
    scores = [min(i["days_late"] or 0, 30) + 15 * (i["repeat_count"] - 1) for i in items]
    assert scores == sorted(scores, reverse=True)
    assert any(i["urgent"] for i in items)


def test_ticket_detail_lists_the_customers_other_tickets(client, repo):
    t = next(iter(repo.tickets.values()))
    detail = client.get(f"/api/cx/tickets/{t['ticket_number']}").json()
    assert all(h["ticket_number"] != t["ticket_number"] for h in detail["history"])

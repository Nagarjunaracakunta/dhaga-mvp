"""HTTP-level tests on demo data with no API key (fallback mode)."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.cx import service

from .conftest import make_deps


@pytest.fixture
def client(repo, settings):
    app.dependency_overrides[service.get_deps] = lambda: make_deps(repo, settings)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_and_filter_tickets(client):
    rows = client.get("/api/cx/tickets").json()
    assert len(rows) == 10 and rows[0]["ticket_number"] == "TKT200001"
    assert client.get("/api/cx/tickets", params={"status": "RESOLVED"}).json() == []
    bad = client.get("/api/cx/tickets", params={"status": "nope"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST"
    assert bad.json()["error"]["details"][0]["field"] == "status"


def test_ticket_detail_by_number_includes_facts(client):
    body = client.get("/api/cx/tickets/TKT200001").json()
    assert body["ticket"]["customer_name"] == "Priya Sharma"
    assert body["facts"]["order_number"] == "DHC100560" and body["facts"]["courier"] == "Delhivery"


def test_unknown_ticket_uses_the_error_shape(client):
    r = client.get("/api/cx/tickets/TKT999999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_analyze_then_approve_resolves_the_ticket(client):
    result = client.post("/api/cx/tickets/TKT200001/analyze").json()
    assert result["status"] == "DRAFTED" and result["fallback_mode"] is True

    listed = client.get("/api/cx/tickets", params={"intent": "WISMO"}).json()
    assert [t["ticket_number"] for t in listed] == ["TKT200001"] and listed[0]["status"] == "DRAFTED"

    decision = client.post("/api/cx/tickets/TKT200001/decision",
                           json={"interaction_id": result["interaction_id"], "action": "APPROVED"})
    assert decision.json() == {"ticket_id": result["ticket_id"], "ticket_status": "RESOLVED", "human_action": "APPROVED"}

    again = client.post("/api/cx/tickets/TKT200001/decision",
                        json={"interaction_id": result["interaction_id"], "action": "APPROVED"})
    assert again.status_code == 409
    assert client.post("/api/cx/tickets/TKT200001/analyze").json()["error"]["code"] == "TICKET_CLOSED"


def test_edit_requires_text_and_escalation_works(client):
    r = client.post("/api/cx/tickets/TKT200027/analyze").json()
    assert r["status"] == "NEEDS_HUMAN" and r["escalation_tier"] == "Tier 2"
    bad = client.post("/api/cx/tickets/TKT200027/decision", json={"interaction_id": r["interaction_id"], "action": "EDITED"})
    assert bad.json()["error"]["code"] == "FINAL_REPLY_REQUIRED"
    ok = client.post("/api/cx/tickets/TKT200027/decision", json={"interaction_id": r["interaction_id"], "action": "ESCALATED"})
    assert ok.json()["ticket_status"] == "ESCALATED"


def test_analyze_pasted_text_and_metrics(client):
    r = client.post("/api/cx/analyze", json={"message": "kab aayega mera order?", "order_number": "dhc100488"}).json()
    assert r["facts"]["order_number"] == "DHC100488" and r["ticket_id"] is None
    m = client.get("/api/cx/metrics").json()
    assert m["analysed"] == 1 and m["fallback_runs"] == 1 and m["by_intent"] == {"WISMO": 1}


def test_order_lookup(client):
    assert client.get("/api/cx/orders/dhc100231").json()["facts"]["days_late"] == 6
    assert client.get("/api/cx/orders/DHC000000").status_code == 404


def test_returns_module_still_mounted(client):
    assert client.get("/api/returns/summary").json()["total_returns"] == 448

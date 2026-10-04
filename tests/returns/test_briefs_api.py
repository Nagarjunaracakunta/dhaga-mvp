"""Brief endpoints via the FastAPI app, with the LLM and store swapped for fakes."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.returns import briefs, router as returns_router
from backend.modules.returns.store import MemoryStore
from backend.shared.llm import LLMResult


class EvidenceAwareLLM:
    """Writer returns a Brief built from the real evidence in the prompt (so it passes the
    deterministic checks); judge always passes. Routes by output_format, so it is robust to
    the regenerate loop."""
    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None,
              allow_fallback_model=False):
        if output_format is briefs.Verdict:
            parsed = briefs.Verdict(passed=True, issues=[])
        else:
            ev = json.loads(re.search(r"<evidence>\n(.*)\n</evidence>", user, re.S).group(1))
            parsed = briefs.Brief(
                headline=f"{ev['product_name']} returns",
                explanation=f"{ev['product_name']} is returned at {ev['return_rate_pct']}% versus "
                            f"{ev['baseline_rate_pct']}% overall.",
                suggested_action="Re-check the size chart with the vendor.")
        return LLMResult(parsed=parsed, model=model, input_tokens=100, output_tokens=20, cost_usd=0.001, latency_ms=2)


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(returns_router, "get_store", lambda: store)
    monkeypatch.setattr(returns_router, "get_llm", lambda: EvidenceAwareLLM())
    returns_router._cache.clear()
    yield store
    returns_router._cache.clear()


def test_generate_then_list_briefs():
    c = TestClient(app)
    gen = c.post("/api/returns/briefs", json={"top_k": 2})
    assert gen.status_code == 200 and gen.json()["generated"] >= 1
    lst = c.get("/api/returns/briefs")
    assert lst.status_code == 200 and len(lst.json()) >= 1
    assert lst.json()[0]["review_status"] == "pending"


def test_review_a_brief():
    c = TestClient(app)
    c.post("/api/returns/briefs", json={"top_k": 1})
    iid = c.get("/api/returns/briefs").json()[0]["insight_id"]
    r = c.post(f"/api/returns/briefs/{iid}/review", json={"status": "approved", "reviewer": "neha"})
    assert r.status_code == 200
    assert c.get("/api/returns/briefs").json()[0]["review_status"] == "approved"

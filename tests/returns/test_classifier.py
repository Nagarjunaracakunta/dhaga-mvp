"""Stage 2: classify "Other" comments, apply them in the pipeline, review them. Fake model: free and repeatable."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.returns import classifier, router as returns_router
from backend.modules.returns.pipeline import run_pipeline
from backend.modules.returns.store import MemoryStore
from backend.shared.llm import LLMResult, LLMUnavailable
from backend.shared.settings import Settings


class FakeLLM:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None,
              allow_fallback_model=False):
        self.calls.append({"model": model, "temperature": temperature, "user": user})
        out = self.fn(user)
        if isinstance(out, Exception):
            raise out
        return LLMResult(parsed=out, model=model, input_tokens=300, output_tokens=20, cost_usd=0.0004, latency_ms=3)


def fit(conf=0.95):
    return classifier.ReturnClassification(category="FIT", sub_reason="TOO_TIGHT", body_area="SHOULDERS", confidence=conf)


def settings():
    return Settings(_env_file=None, supabase_url="", supabase_service_key="", anthropic_api_key="", openrouter_api_key="")


def test_classify_comments_runs_in_parallel_at_temperature_0():
    llm = FakeLLM(lambda u: fit())
    run = classifier.classify_comments(llm, settings(), {f"r{i}": "shoulders pe tight" for i in range(20)})
    assert len(run["results"]) == 20 and not run["failed"] and run["cost_usd"] == pytest.approx(0.008)
    assert run["results"]["r0"] == {"ai_category": "FIT", "ai_subcategory": "TOO_TIGHT:SHOULDERS", "ai_confidence": 0.95}
    assert all(c["temperature"] == 0 and c["model"] == "claude-haiku-4-5" for c in llm.calls)


def test_failures_are_reported_not_hidden():
    run = classifier.classify_comments(FakeLLM(lambda u: LLMUnavailable("down")), settings(), {"r1": "x"})
    assert run["results"] == {} and "unavailable" in run["failed"]["r1"]


def test_pipeline_uses_ai_and_human_reasons():
    base = run_pipeline()
    pending = base.returns[base.returns["classification_source"] == "pending_llm"]["return_id"].tolist()
    store = MemoryStore()
    store.save_ai({pending[0]: {"ai_category": "FIT", "ai_subcategory": "TOO_TIGHT:SHOULDERS", "ai_confidence": 0.9},
                   pending[1]: {"ai_category": "UNCLEAR", "ai_subcategory": None, "ai_confidence": 0.4}}, None)
    store.set_final(pending[2], "QUALITY", None)
    store.save_ai({pending[2]: {"ai_category": "FIT", "ai_subcategory": "TOO_TIGHT:WAIST", "ai_confidence": 0.8}}, None)
    res = run_pipeline(store=store)
    r = res.returns.set_index("return_id")
    assert (r.at[pending[0], "primary_reason"], r.at[pending[0], "body_area"], r.at[pending[0], "classification_source"]) \
        == ("FIT", "SHOULDERS", "ai")
    assert r.at[pending[1], "classification_source"] == "ai_review"          # unclear -> a person checks
    assert r.at[pending[2], "primary_reason"] == "QUALITY" and pd.isna(r.at[pending[2], "sub_reason"])  # human wins
    s = res.summary
    assert s["other_pending"] == base.summary["other_pending"] - 3
    assert (s["ai_classified"], s["needs_review"], s["human_reviewed"]) == (2, 1, 1)


@pytest.fixture
def client(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(returns_router, "get_store", lambda: store)
    monkeypatch.setattr(returns_router, "get_llm", lambda: FakeLLM(
        lambda u: fit(0.5) if "ok" in u.lower() else fit()))
    returns_router._cache.clear()
    yield TestClient(app)
    returns_router._cache.clear()


def test_classify_then_review_endpoints(client):
    before = client.get("/api/returns/summary").json()
    out = client.post("/api/returns/classify", json={"limit": 50}).json()
    assert out["classified"] == 50 and out["failed"] == 0
    after = client.get("/api/returns/summary").json()
    assert after["other_pending"] == before["other_pending"] - 50 and after["ai_classified"] == 50

    queue = client.get("/api/returns/review-queue", params={"include_confident": True}).json()
    rid = queue[0]["return_id"]
    assert client.post(f"/api/returns/{rid}/review", json={"category": "FIT"}).json()["action"] == "accepted"
    assert client.post(f"/api/returns/{rid}/review", json={"category": "COLOUR"}).json()["action"] == "corrected"
    assert client.get("/api/returns/summary").json()["human_reviewed"] == 1
    assert client.post("/api/returns/nope/review", json={"category": "FIT"}).json()["error"]["code"] == "RETURN_NOT_FOUND"
    assert client.post(f"/api/returns/{rid}/review", json={"category": "BAD"}).status_code == 422


def test_insights_carry_sample_returns_with_reasons(client):
    client.post("/api/returns/classify", json={"limit": 500})
    ins = client.get("/api/returns/insights").json()
    samples = [s for i in ins for s in i["sample_returns"]]
    assert samples and all({"comment", "reason", "source"} <= s.keys() for s in samples)
    assert any(s["source"] in ("ai", "ai_review") for s in samples)

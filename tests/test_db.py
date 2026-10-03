import os
import pytest
from sqlalchemy import create_engine
from ai.classifier import classify_comments
from ai.cost import CostTracker
from ai.llm import ModelSpec
from ai.run import run
from db import store

MOCK = ModelSpec.parse("mock:mock")


def _engines(tmp_path):
    yield "sqlite", store.get_engine(f"sqlite:///{tmp_path / 't.db'}")
    url = os.getenv("TEST_DATABASE_URL")          # optional: run the same tests against real Postgres/Supabase
    if url:
        yield "postgres", store.get_engine(url)


def test_normalize_url():
    assert store.normalize_url("postgres://u:p@h:6543/postgres") == "postgresql+psycopg://u:p@h:6543/postgres"
    assert store.normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert store.normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_run_persists_and_review_workflow(tmp_path):
    for name, eng in _engines(tmp_path):
        store.init_schema(eng)
        _, recs, report = run(MOCK, MOCK, out_dir=tmp_path, engine=eng)
        rid = report["run_id"]
        counts = store.table_counts(eng)
        assert counts["runs"] >= 1 and counts["returns"] > 400 and counts["insights"] >= len(recs) > 0, name
        assert store.latest_run_id(eng) == rid
        rows = store.list_insights(eng, rid)
        assert rows[0]["review_status"] == "pending" and rows[0]["recommendation"]["headline"]
        assert store.set_review(eng, rid, rows[0]["insight_id"], "approved", "neha", "looks right")
        assert not store.set_review(eng, rid, "does-not-exist", "approved")
        assert store.list_insights(eng, rid, "approved")[0]["reviewer"] == "neha"
        with pytest.raises(ValueError):
            store.set_review(eng, rid, rows[0]["insight_id"], "maybe")
        # re-saving the same run must NOT wipe the human decision
        store.save_insights(eng, rid, recs)
        assert store.list_insights(eng, rid, "approved")
        assert store.get_run_report(eng, rid)["cost"]["calls"] >= 0
        assert len(store.get_returns(eng, primary_reason="FIT", limit=5)) > 0


def test_db_cache_shared_across_runs(tmp_path):
    for name, eng in _engines(tmp_path):
        store.init_schema(eng)
        cache = store.DbCache(eng)
        t1, t2 = CostTracker(), CostTracker()
        classify_comments(["waist loose hai " + name], MOCK, MOCK, t1, cache, escalate=False)
        _, stats = classify_comments(["waist loose hai " + name], MOCK, MOCK, t2, store.DbCache(eng), escalate=False)
        assert t1.calls == 1 and t2.calls == 0 and stats["cache_hits"] == 1

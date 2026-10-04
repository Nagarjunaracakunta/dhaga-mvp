"""Brief persistence in MemoryStore (Supabase path is exercised live, not in unit tests)."""
from backend.modules.returns.store import MemoryStore


def record(iid="product_size:P1|M"):
    return {"insight_id": iid, "product_id": "P1", "product_name": "Floral Midi Dress",
            "brief": {"headline": "h", "explanation": "e", "suggested_action": "a"},
            "status": "passed_checks", "open_issues": [], "attempts": 1,
            "model": "claude-sonnet-5-5", "cost_usd": 0.004}


def test_memory_store_saves_and_lists_briefs():
    s = MemoryStore()
    s.save_brief(record())
    got = s.get_briefs()
    assert len(got) == 1 and got[0]["insight_id"] == "product_size:P1|M"
    assert got[0]["review_status"] == "pending"


def test_memory_store_save_brief_is_idempotent_on_insight_id():
    s = MemoryStore()
    s.save_brief(record())
    s.save_brief({**record(), "status": "needs_manual_review"})
    assert len(s.get_briefs()) == 1 and s.get_briefs()[0]["status"] == "needs_manual_review"


def test_memory_store_review_updates_status_and_note():
    s = MemoryStore()
    s.save_brief(record())
    s.set_brief_review("product_size:P1|M", "approved", "neha", "check vendor size chart")
    b = s.get_briefs()[0]
    assert (b["review_status"], b["reviewer"], b["review_note"]) == ("approved", "neha", "check vendor size chart")


def test_supabase_store_saves_only_table_columns(monkeypatch):
    """The brief result carries latency_ms for the run log; returns_briefs has no such column."""
    import re
    from pathlib import Path

    from backend.modules.returns import store as store_mod

    sql = (Path(__file__).resolve().parents[2] / "db" / "returns_tables.sql").read_text()
    columns = set(re.findall(r"^\s{4}(\w+)\s", sql, re.M))
    sent = {}

    class Table:
        def upsert(self, row, on_conflict):
            sent.update(row)
            return self

        def execute(self):
            unknown = set(sent) - columns
            assert not unknown, f"columns not in returns_briefs: {unknown}"

    monkeypatch.setattr(store_mod, "get_supabase", lambda: type("SB", (), {"table": lambda self, name: Table()})())
    store_mod.SupabaseStore().save_brief({"insight_id": "x", "product_id": "p", "product_name": "P", "brief": {},
                                          "status": "passed_checks", "open_issues": [], "attempts": 1,
                                          "model": "m", "cost_usd": 0.01, "latency_ms": 1200})
    assert sent["insight_id"] == "x" and "latency_ms" not in sent

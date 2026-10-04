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

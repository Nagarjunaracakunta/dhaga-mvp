"""Where return classifications are saved. Supabase writes the returns table; Memory is for the demo CSVs."""
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from backend.shared.db import execute, get_supabase

log = logging.getLogger(__name__)
BRIEF_COLUMNS = {"insight_id", "product_id", "product_name", "brief", "status", "open_issues", "attempts", "model",
                 "cost_usd"}
WORKFLOW = "RETURNS_CLASSIFIER"
FIELDS = ["ai_category", "ai_subcategory", "ai_confidence", "final_category"]


class MemoryStore:
    """Demo CSV mode: results live until the server restarts."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.briefs: dict[str, dict] = {}

    def save_ai(self, results: dict[str, dict], returns: pd.DataFrame) -> None:
        for rid, fields in results.items():
            self.rows.setdefault(rid, {}).update(fields)

    def set_final(self, return_id: str, category: Optional[str], returns: pd.DataFrame) -> None:
        self.rows.setdefault(return_id, {})["final_category"] = category

    def overlay(self, returns: pd.DataFrame) -> pd.DataFrame:
        df = returns.copy()
        for col in FIELDS:
            if col not in df.columns:
                df[col] = None
        for rid, fields in self.rows.items():
            mask = df["return_id"] == rid
            for col, val in fields.items():
                df.loc[mask, col] = val
        return df

    def log_run(self, row: dict) -> None:
        pass

    def save_brief(self, record: dict) -> None:
        iid = record["insight_id"]
        existing = self.briefs.get(iid, {"review_status": "pending", "reviewer": None, "review_note": None})
        self.briefs[iid] = {**existing, **record}

    def get_briefs(self) -> list[dict]:
        return list(self.briefs.values())

    def set_brief_review(self, insight_id, status, reviewer=None, note=None) -> None:
        self.briefs.setdefault(insight_id, {"insight_id": insight_id})
        self.briefs[insight_id].update(review_status=status, reviewer=reviewer, review_note=note)


class SupabaseStore:
    def save_ai(self, results: dict[str, dict], returns: pd.DataFrame) -> None:
        keys = returns.set_index("return_id")[["order_item_id", "customer_id"]].to_dict("index")
        rows = [{"return_id": rid, **keys[rid], **fields} for rid, fields in results.items() if rid in keys]
        for i in range(0, len(rows), 200):  # upsert needs the NOT NULL columns; only these columns change
            get_supabase().table("returns").upsert(rows[i:i + 200], on_conflict="return_id").execute()

    def set_final(self, return_id: str, category: Optional[str], returns: pd.DataFrame) -> None:
        get_supabase().table("returns").update({"final_category": category}).eq("return_id", return_id).execute()

    def overlay(self, returns: pd.DataFrame) -> pd.DataFrame:
        return returns  # already loaded with the ai_* columns

    def log_run(self, row: dict) -> None:
        try:
            get_supabase().table("ai_interactions").insert({"workflow": WORKFLOW, **row}).execute()
        except Exception:
            log.exception("Could not log the returns classification run")

    def save_brief(self, record: dict) -> None:
        # Only the columns in db/returns_tables.sql; extra fields (e.g. latency_ms, used for the run log) are rejected
        row = {k: v for k, v in record.items() if k in BRIEF_COLUMNS}
        get_supabase().table("returns_briefs").upsert(row, on_conflict="insight_id").execute()

    def get_briefs(self) -> list[dict]:
        return execute(get_supabase().table("returns_briefs").select("*")).data or []

    def set_brief_review(self, insight_id, status, reviewer=None, note=None) -> None:
        get_supabase().table("returns_briefs").update(
            {"review_status": status, "reviewer": reviewer, "review_note": note,
             "reviewed_at": datetime.now(timezone.utc).isoformat()}).eq("insight_id", insight_id).execute()

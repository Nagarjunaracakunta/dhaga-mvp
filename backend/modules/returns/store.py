"""Where return classifications are saved. Supabase writes the returns table; Memory is for the demo CSVs."""
import logging
from typing import Optional

import pandas as pd

from backend.shared.db import get_supabase

log = logging.getLogger(__name__)
WORKFLOW = "RETURNS_CLASSIFIER"
FIELDS = ["ai_category", "ai_subcategory", "ai_confidence", "final_category"]


class MemoryStore:
    """Demo CSV mode: results live until the server restarts."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

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

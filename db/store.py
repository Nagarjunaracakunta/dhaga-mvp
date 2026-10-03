"""Persistence layer. Works on SQLite (default, zero setup) and Postgres/Supabase (set DATABASE_URL)."""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, select, text, update, func
from sqlalchemy.engine import Engine

from backend import config as bconfig
from .models import metadata, runs, returns, insights, llm_cache

REVIEW_STATUSES = {"pending", "approved", "dismissed", "needs_followup"}
_CHUNK = 500


def normalize_url(url: str) -> str:
    """Accept the strings Supabase shows (postgres://...) and select the psycopg3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine(url: Optional[str] = None) -> Engine:
    url = normalize_url(url or os.getenv("DATABASE_URL") or f"sqlite:///{bconfig.PROCESSED_DIR / 'dhaga.db'}")
    if url.startswith("sqlite"):
        bconfig.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        return create_engine(url)
    # prepare_threshold=None: Supabase's transaction pooler (port 6543) does not support prepared statements.
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                         connect_args={"prepare_threshold": None})


def init_schema(engine: Engine):
    metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine: Engine):
    """Tiny migration: add columns introduced after a database was first created."""
    insp = inspect(engine)
    if "insights" in insp.get_table_names() and "sample_comments" not in {c["name"] for c in insp.get_columns("insights")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE insights ADD COLUMN sample_comments " + ("JSONB" if engine.dialect.name == "postgresql" else "JSON")))


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _now():
    return datetime.now(timezone.utc)


def _clean(obj):
    """Make nested data JSON-safe (numpy scalars, enums, timestamps)."""
    return json.loads(json.dumps(obj, default=str))


def _insert_fn(engine):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def _upsert(engine, table, rows: list, keys: list, skip_update=()):
    if not rows:
        return
    ins = _insert_fn(engine)(table)
    stmt = ins.on_conflict_do_update(
        index_elements=keys,
        set_={c.name: ins.excluded[c.name] for c in table.columns if c.name not in keys and c.name not in skip_update})
    with engine.begin() as conn:
        for i in range(0, len(rows), _CHUNK):
            conn.execute(stmt, rows[i:i + _CHUNK])


# ---------------- writes ----------------
def save_run(engine, run_id: str, fast: str, strong: str, report: dict):
    cost = report.get("cost", {})
    _upsert(engine, runs, [{
        "run_id": run_id, "created_at": _now(), "fast_model": fast, "strong_model": strong,
        "est_usd": cost.get("estimated_usd"), "llm_calls": cost.get("calls"), "report": _clean(report)}], ["run_id"])


_RETURN_COLS = [c.name for c in returns.columns if c.name != "run_id"]


def save_returns(engine, df: pd.DataFrame, run_id: str):
    d = df.reindex(columns=_RETURN_COLS).copy()
    d["return_date"] = pd.to_datetime(d["return_date"]).dt.date
    d = d.astype(object).where(pd.notna(d), None)
    rows = [{**r, "run_id": run_id} for r in d.to_dict("records")]
    _upsert(engine, returns, rows, ["return_id"])


def save_insights(engine, run_id: str, recs: list):
    """recs: items from ai.run (insight + evidence + status + recommendation). Review fields start as 'pending'."""
    rows = []
    for r in recs:
        ins = r["insight"]
        rows.append({
            "run_id": run_id, "insight_id": r["insight_id"], "product_id": str(ins["product_id"]),
            "product_name": ins["product_name"], "segment": _clean(ins["segment"]),
            "orders": ins["orders"], "returns_count": ins["returns"], "return_rate": ins["return_rate"], "lift": ins["lift"],
            "evidence": _clean(r["evidence"]), "recommendation": _clean(r["recommendation"]),
            "sample_comments": _clean(ins.get("sample_comments", [])),
            "status": r["status"], "attempts": r["attempts"], "open_issues": _clean(r["open_issues"]),
            "review_status": "pending"})
    _upsert(engine, insights, rows, ["run_id", "insight_id"],
            skip_update=("review_status", "reviewer", "review_note", "reviewed_at"))


def set_review(engine, run_id: str, insight_id: str, status: str, reviewer: str = None, note: str = None) -> bool:
    """Record the human decision. Returns False if the insight does not exist."""
    if status not in REVIEW_STATUSES:
        raise ValueError(f"status must be one of {sorted(REVIEW_STATUSES)}")
    with engine.begin() as conn:
        res = conn.execute(update(insights).where(insights.c.run_id == run_id, insights.c.insight_id == insight_id)
                           .values(review_status=status, reviewer=reviewer, review_note=note, reviewed_at=_now()))
    return res.rowcount > 0


# ---------------- reads ----------------
def latest_run_id(engine) -> Optional[str]:
    with engine.connect() as conn:
        return conn.execute(select(runs.c.run_id).order_by(runs.c.created_at.desc()).limit(1)).scalar()


def list_runs(engine, limit=20) -> list:
    with engine.connect() as conn:
        rows = conn.execute(select(runs.c.run_id, runs.c.created_at, runs.c.fast_model, runs.c.strong_model,
                                   runs.c.est_usd, runs.c.llm_calls).order_by(runs.c.created_at.desc()).limit(limit))
        return [dict(r._mapping) for r in rows]


def get_run_report(engine, run_id: str) -> Optional[dict]:
    with engine.connect() as conn:
        v = conn.execute(select(runs.c.report).where(runs.c.run_id == run_id)).scalar()
    return json.loads(v) if isinstance(v, str) else v


def list_insights(engine, run_id: str = None, review_status: str = None) -> list:
    run_id = run_id or latest_run_id(engine)
    q = select(insights).where(insights.c.run_id == run_id).order_by(insights.c.lift.desc())
    if review_status:
        q = q.where(insights.c.review_status == review_status)
    with engine.connect() as conn:
        out = []
        for r in conn.execute(q):
            d = dict(r._mapping)
            for k in ("segment", "evidence", "recommendation", "open_issues", "sample_comments"):
                if isinstance(d[k], str):
                    d[k] = json.loads(d[k])
            out.append(d)
        return out


def get_returns(engine, product_id: str = None, primary_reason: str = None, limit: int = 100) -> pd.DataFrame:
    q = select(returns).limit(limit)
    if product_id:
        q = q.where(returns.c.product_id == product_id)
    if primary_reason:
        q = q.where(returns.c.primary_reason == primary_reason)
    with engine.connect() as conn:
        return pd.read_sql(q, conn)


def table_counts(engine) -> dict:
    """Row count per table; None for a table that does not exist yet (run `python -m db.cli init`)."""
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        return {t.name: (conn.execute(select(func.count()).select_from(t)).scalar() if t.name in existing else None)
                for t in metadata.sorted_tables}


# ---------------- LLM cache (same interface as ai.cache.ClassificationCache) ----------------
class DbCache:
    def __init__(self, engine):
        self.engine = engine

    def get_many(self, keys: list) -> dict:
        out = {}
        with self.engine.connect() as conn:
            for i in range(0, len(keys), _CHUNK):
                chunk = keys[i:i + _CHUNK]
                out.update({k: v for k, v in conn.execute(
                    select(llm_cache.c.key, llm_cache.c.value).where(llm_cache.c.key.in_(chunk)))})
        return out

    def put_many(self, rows: dict):
        _upsert(self.engine, llm_cache, [{"key": k, "value": v, "created_at": _now()} for k, v in rows.items()], ["key"])

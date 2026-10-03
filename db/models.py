"""Table definitions (SQLAlchemy Core). One source of truth for SQLite (local) and Postgres (Supabase)."""
from sqlalchemy import (Column, Date, DateTime, Float, Integer, JSON, MetaData, String, Table, Text, Index)
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")
metadata = MetaData()

# One row per pipeline/AI run: which models, what it cost, the full report (for the UI + audit).
runs = Table(
    "runs", metadata,
    Column("run_id", String, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("fast_model", String), Column("strong_model", String),
    Column("est_usd", Float), Column("llm_calls", Integer),
    Column("report", JSONType),
)

# Latest cleaned + classified state of each return (upserted by return_id).
returns = Table(
    "returns", metadata,
    Column("return_id", String, primary_key=True),
    Column("order_id", String), Column("product_id", String, index=True),
    Column("product_name", String), Column("category", String),
    Column("size", String), Column("colour", String),
    Column("return_reason", String), Column("return_comment", Text), Column("return_date", Date),
    Column("primary_reason", String), Column("sub_reason", String), Column("body_area", String),
    Column("classification_source", String), Column("confidence", Float),
    Column("run_id", String),
)

# Candidate insights + the generated brief + the HUMAN decision on it (the review workflow lives here).
insights = Table(
    "insights", metadata,
    Column("run_id", String, primary_key=True),
    Column("insight_id", String, primary_key=True),
    Column("product_id", String), Column("product_name", String),
    Column("segment", JSONType),
    Column("orders", Integer), Column("returns_count", Integer),
    Column("return_rate", Float), Column("lift", Float),
    Column("evidence", JSONType), Column("recommendation", JSONType), Column("sample_comments", JSONType),
    Column("status", String),                      # passed_checks | needs_manual_review (set by code)
    Column("attempts", Integer), Column("open_issues", JSONType),
    Column("review_status", String, nullable=False, server_default="pending"),  # pending|approved|dismissed|needs_followup
    Column("reviewer", String), Column("review_note", Text), Column("reviewed_at", DateTime(timezone=True)),
)

# Shared LLM cache so every deployment/restart reuses earlier classifications (HF Spaces disk is ephemeral).
llm_cache = Table(
    "llm_cache", metadata,
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)
Index("ix_insights_review", insights.c.review_status)

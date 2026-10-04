-- Returns briefs: one LLM-written, fact-checked investigation brief per flagged insight.
-- Paste into the Supabase SQL editor. Keyed by the deterministic insight_id string.
CREATE TABLE IF NOT EXISTS returns_briefs (
    insight_id    TEXT PRIMARY KEY,
    product_id    TEXT,
    product_name  TEXT,
    brief         JSONB,
    status        TEXT,
    open_issues   JSONB,
    attempts      INTEGER,
    model         TEXT,
    cost_usd      NUMERIC,
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewer      TEXT,
    review_note   TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    reviewed_at   TIMESTAMPTZ
);
ALTER TABLE returns_briefs ENABLE ROW LEVEL SECURITY;

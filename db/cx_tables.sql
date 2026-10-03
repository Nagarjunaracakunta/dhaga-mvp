-- CX Copilot setup: the two tables the app needs that are not in the database yet.
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.
-- Safe to run again (IF NOT EXISTS).

-- Every Copilot run and the agent's decision.
-- Owner: cx module (Returns stage 2 will also write rows with workflow = 'RETURNS_CLASSIFIER').
CREATE TABLE IF NOT EXISTS ai_interactions (
    interaction_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow             TEXT NOT NULL,              -- 'CX_COPILOT'
    input_reference_type TEXT,                       -- 'support_ticket'
    input_reference_id   UUID,                       -- support_tickets.ticket_id (null for pasted text)
    model_name           TEXT,
    prompt_version       TEXT,
    input_summary        TEXT,
    output               JSONB,                      -- full CopilotResult + final_reply after the decision
    confidence           DECIMAL(5,4),
    evaluation_status    TEXT,                       -- PASSED / REVIEW_REQUIRED / FAILED
    human_action         TEXT,                       -- APPROVED / EDITED / REJECTED / ESCALATED
    processing_time_ms   INTEGER,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_interactions_ref
    ON ai_interactions (workflow, input_reference_id, created_at);

-- Metadata for policy PDFs stored in the Supabase Storage bucket (Dhaga).
-- storage_path is the path inside the bucket, e.g. 'policies/delivery_faq.pdf'.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_name TEXT NOT NULL,
    document_type TEXT NOT NULL,                     -- delivery / cancellation / returns / cod / escalation
    storage_path  TEXT,
    version       TEXT,
    active        BOOLEAN DEFAULT TRUE,
    description   TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- The backend uses the secret key, which bypasses Row Level Security. Turn RLS on so the
-- publishable (browser) key cannot read these tables.
ALTER TABLE ai_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;

-- Lock down the existing tables too. Right now the publishable key can read customer names,
-- emails and phone numbers. The backend uses the secret key, so it is not affected.
ALTER TABLE customers           ENABLE ROW LEVEL SECURITY;
ALTER TABLE products            ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders              ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets     ENABLE ROW LEVEL SECURITY;
ALTER TABLE returns             ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews             ENABLE ROW LEVEL SECURITY;

-- Make the new tables visible to the API immediately
NOTIFY pgrst, 'reload schema';

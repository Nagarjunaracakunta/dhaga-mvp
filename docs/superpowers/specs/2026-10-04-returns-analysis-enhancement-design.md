# Returns Analysis Enhancement — Design

**Date:** 2026-10-04
**Branch:** `feat/returns-analysis-enhance` → PR into `Nagarjunaracakunta/dhaga-mvp` `main`

## Problem

Main's returns analysis classifies "Other" comments with a single model (Haiku 4.5)
and surfaces insights as pure statistics. Neha (Category Head) reads the "Other" box
by hand because the system gives her no readable, trustworthy explanation of *why* a
segment is being returned, and low-confidence classifications are dumped straight onto
humans instead of being retried. We are porting the two signature patterns from PR 3
(the earlier Streamlit build) onto main's Supabase/FastAPI/React foundation, plus a
prompt-quality and human-review improvement.

## Goals (the four gaps the client picked)

1. **Routing / escalation** — low-confidence Haiku classifications are retried on a
   stronger model before a human is bothered.
2. **Evaluator-optimizer briefs** — an LLM writes a plain-language investigation brief
   per flagged insight; a second model fact-checks it against the real numbers; it
   loops until it passes or is flagged for manual read.
3. **Classification depth** — a richer classify prompt (v2) with more Hinglish coverage.
4. **Insight-level human review** — approve / needs-follow-up / dismiss + a note on each
   brief, persisted and shown in the UI.

## Decisions (locked)

- **Strong model = Sonnet 5.5** (`claude-sonnet-5-5`). Accepts `temperature=0` (Opus
  does not), already in `settings.price_per_mtok`, cheaper than Opus. Used for both
  escalation and brief writing.
- **Brief storage = new `returns_briefs` Supabase table**, keyed by `insight_id`.
  `MemoryStore` mirrors it in a dict for CSV/demo mode.
- **Taxonomy = prompt v2 only.** No enum changes, so no DB-value or UI `CATEGORIES`
  churn.

## Model / temperature split (project ground rules)

| Step | Model | Temp | Why a model (not code) |
|---|---|---|---|
| Classify (bulk) | Haiku 4.5 | 0 | Hinglish free-text → taxonomy |
| Escalate (≤20% uncertain) | Sonnet 5.5 | 0 | harder language calls |
| Brief writer | Sonnet 5.5 | 0.3 | prose from evidence; regeneration must differ |
| Brief judge | Haiku 4.5 | 0 | cheap fact-check verdict |

Two models minimum satisfied: Haiku (bulk + judge) + Sonnet (escalation + writer).
All arithmetic, aggregation, lift and the deterministic brief checks are plain Python.

## Architecture

### Backend (`backend/modules/returns/`)

- **`classifier.py`** — add escalation inside `classify_comments`: first pass on
  `model_fast`; collect results with `confidence < ESCALATE_BELOW` (0.70) that are not
  failures; cap at `MAX_ESCALATION_SHARE` (0.20) of unique comments; re-run that subset
  on `model_strong` at temp 0; keep the strong result when its confidence is higher.
  Return dict gains `escalated` (count) and `strong_model`. Per-return stored columns are
  unchanged (no DB churn); escalation shows in the run summary and `ai_interactions` log.
- **`briefs.py`** (new) — the evaluator-optimizer:
  - `Brief` schema `{headline: str, explanation: str, suggested_action: str}`.
  - `Verdict` schema `{passed: bool, issues: list[str]}`.
  - `build_evidence(insight) -> dict` — deterministic numbers the brief must be true to.
  - `deterministic_checks(brief, insight) -> list[str]` — product name present,
    return-rate figure present, explanation ≤ `MAX_BRIEF_WORDS` (80), action non-empty.
  - `generate_brief(llm, settings, insight) -> dict` — loop ≤ `MAX_BRIEF_ATTEMPTS` (3):
    write (Sonnet, 0.3) → deterministic checks → judge (Haiku, 0) → regenerate with the
    issues as feedback. Returns `{insight_id, product_id, product_name, brief, status,
    open_issues, attempts, model, cost_usd, latency_ms}` where `status` ∈
    `{"passed_checks", "needs_manual_review"}`.
  - Prompts: `prompts/write_brief_v1.md`, `prompts/judge_brief_v1.md`.
- **`store.py`** — add to both stores: `save_brief(record)`, `get_briefs() -> list[dict]`,
  `set_brief_review(insight_id, status, reviewer, note)`. Supabase writes
  `returns_briefs`; Memory keeps `self.briefs: dict[str, dict]`.
- **`router.py`** — `POST /briefs` `{top_k, redo}` (generate for top-K candidate
  insights, persist), `GET /briefs` (persisted briefs enriched with live evidence; mark
  `stale` if the `insight_id` no longer flags), `POST /briefs/{insight_id}/review`
  `{status, reviewer?, note?}`; `/classify` response gains `escalated`.
- **`config.py`** — add `ESCALATE_BELOW=0.70`, `MAX_ESCALATION_SHARE=0.20`,
  `TOP_K_BRIEFS=5`, `MAX_BRIEF_ATTEMPTS=3`, `MAX_BRIEF_WORDS=80`.
- **`db/returns_tables.sql`** (new) — `returns_briefs` table + RLS enable.

### Frontend (`frontend/src/`)

- **`api.js`** — `returnsBriefs()`, `returnsGenerateBriefs({topK})`,
  `returnsBriefReview(insightId, status, note)`.
- **`Returns.jsx`** — new "Investigation briefs" panel: a "Generate briefs" button and a
  ranked list of brief cards (severity by lift: High ≥2×, Medium ≥1.6×, else Low). Each
  card shows headline, explanation, suggested action, a red banner if
  `status==="needs_manual_review"` (with `open_issues`), the reason mix + sample quotes,
  and review controls (approve / needs-follow-up / dismiss + note). The classify result
  toast reports the `escalated` count.

## `returns_briefs` schema

```sql
CREATE TABLE IF NOT EXISTS returns_briefs (
    insight_id    TEXT PRIMARY KEY,
    product_id    TEXT,
    product_name  TEXT,
    brief         JSONB,
    status        TEXT,              -- passed_checks | needs_manual_review
    open_issues   JSONB,
    attempts      INTEGER,
    model         TEXT,
    cost_usd      NUMERIC,
    review_status TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|needs_followup|dismissed
    reviewer      TEXT,
    review_note   TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    reviewed_at   TIMESTAMPTZ
);
ALTER TABLE returns_briefs ENABLE ROW LEVEL SECURITY;
```

## Failure behaviour (fails visibly)

- Escalation model unavailable → keep the fast result; `escalated` reports what actually
  ran; never crash the classify call.
- Brief writer/judge `LLMUnavailable` or `LLMOutputError` → brief saved with
  `status="needs_manual_review"` and the error in `open_issues`; UI shows the red banner.
- A persisted brief whose `insight_id` no longer flags → returned with `stale: true`.

## Testing

- **Backend (pytest, `FakeLLM`)**: escalation retries only low-confidence items and
  respects the 20% cap and temp 0; `deterministic_checks` catches a missing number /
  missing product name / over-long explanation; `generate_brief` passes on a clean draft,
  regenerates on judge issues, and flags `needs_manual_review` after 3 attempts;
  `MemoryStore` save/get/review round-trips; router `/briefs` endpoints via `TestClient`
  with the LLM dependency overridden.
- **Frontend**: manual via `npm run dev` (no JS test harness in repo) — generate briefs,
  see ranked cards, trip the failure banner, review persists across reload.

## Out of scope

- No new taxonomy categories. No per-return "which model" column. No change to the CX
  copilot. No rework of the existing statistical aggregation beyond feeding briefs.

# 2. Architecture

**Principle:** use deterministic code wherever the answer is known; use an LLM only where understanding messy human language
or writing a judgment requires it.

## Pipeline

```
 raw CSVs (orders, returns, products)
        |
        v
 [CODE] ingest -> validate -> normalize          backend/ingestion.py, validation.py, normalization.py
        |   (bad rows -> rejected_records.csv with a reason; never silently dropped)
        v
 return_reason == "Other" AND comment present?
     |-- no  --> keep dropdown label (or NO_COMMENT)            (no model call)
     '-- yes
        v
 [CODE] skip junk ("."), dedupe identical comments, cache lookup, batch into groups of 25     ai/classifier.py, cache.py
        v
 [LLM #1  FAST model] comment -> {primary, sub, body_area, confidence}  (structured JSON)
        |   confidence < 0.6  --> retry on STRONG model (capped share)  (cascade)
        v
 [CODE] validate schema + taxonomy combo, clamp confidence, apply threshold      ai/apply.py
        |   still < 0.6 -> UNCLEAR (flagged), model failure -> UNCLEAR (flagged)
        v
 [CODE] aggregate: counts, return rates by product/size/colour/reason            backend/aggregation.py
 [CODE] detect candidate insights: min sample, rate >= 1.5x overall, >= 1.4x own product   backend/insights.py
        v
 [LLM #2  STRONG model] verified evidence -> {headline, explanation, action}     ai/recommender.py
        v
 [CODE] evaluator: numbers all in evidence? product named? length? action present?   ai/evaluator.py
 [LLM #3  FAST model] fact-check judge (only if code checks passed)
        |   fail -> regenerate with the issues as feedback (max 3 attempts)  (evaluator-optimizer)
        v
 [DB] persist run, returns, insights, shared LLM cache (SQLite local / Postgres = Supabase)      db/store.py  (docs/04)
        v
 human review (Neha): passed_checks  |  needs_manual_review  -> approve / dismiss / follow up (stored)   (frontend next)
```

## Code vs LLM: who does what

| Step | Code | LLM | Why |
|---|:-:|:-:|---|
| Read CSV, validate columns/dates/ids, reject malformed rows | x | | Exact rules, zero tolerance for guessing |
| Normalize size / colour / dropdown reason | x | | Finite known mappings |
| Dedupe, cache, batch, budget guard | x | | Cost control is plumbing, not judgment |
| Understand Hinglish comments | | x | Messy language; lookup tables cannot cover it |
| Map comment -> taxonomy (reason, sub-reason, body area) | | x | Language -> controlled vocabulary |
| Validate LLM output (schema, allowed combos, confidence range) | x | | Never trust model output unchecked |
| Confidence threshold / accept-or-flag | x | | Policy decision, deterministic |
| Counts, return rates, lift, which segments are notable | x | | Arithmetic and filtering must be exact |
| Write the business explanation | | x | Natural-language judgment |
| Check numbers/product/length in the explanation | x | | Exact check, free |
| Check unsupported claims / overconfident causes | | x (fast) | Semantic check code cannot do |
| Final approval | human | | Accountability |

## Where the LLM is used (and where it deliberately is not)
Three calls only, all behind structured-output schemas (`ai/schemas.py`): **(1) comment classifier**, **(2) recommendation writer**, **(3) fact-check judge**.
The LLM never sees full tables, never aggregates, never decides what is "important" (code finds candidates first), and never sees customer IDs.
Only the free-text comment is sent in step 1; only pre-computed aggregates and a handful of themes are sent in step 2.

## Key design decisions
1. **Deterministic first, AI second.** Stage 1 (no AI) was built and tested before any model call existed.
2. **Controlled taxonomy** (`ai/taxonomy.py`): the model fills a fixed enum; code rejects invalid combinations.
3. **Cascade** instead of one big model: cheap model for everything, strong model only for low-confidence items.
4. **Evaluator-optimizer** for recommendations: generate -> check -> regenerate with feedback; after 3 failures hand to a human.
5. **LangChain used narrowly**: `prompt | model.with_structured_output(schema)` plus `with_retry` and `with_fallbacks`.
   It buys provider-independence (Anthropic and OpenAI are both wired up); we avoid agents/tools because the flow is fixed and must be predictable.
6. **Mock provider** (`mock:mock`) so the full flow runs offline and in CI without keys.

## Failure handling

| Failure | Behaviour |
|---|---|
| Malformed input row | Rejected with reason, listed in `rejected_records.csv` |
| Provider error / rate limit | `with_retry` (3 attempts), then optional `LLM_FALLBACK` model, then item marked `failed` -> `UNCLEAR` + flagged |
| Model returns invalid JSON / missing ids / invalid taxonomy combo | Only the bad items are retried once; still bad -> `failed` |
| Low confidence | Escalate to strong model (capped); still low -> `UNCLEAR` (`llm_low_confidence`), original label kept in `llm_primary` for audit |
| Budget (USD or call count) exceeded | Remaining comments stay `pending_llm` (not misclassified); run report shows how many were skipped |
| Recommendation fails checks 3x | `needs_manual_review` with the open issues listed |

## Code map
```
backend/   no-AI pipeline + API (FastAPI)       ai/   LLM layer (LangChain)
  ingestion, validation, normalization            config.py     all knobs, prices, thresholds
  aggregation, insights, pipeline, main           taxonomy.py   controlled vocabulary
scripts/generate_demo_data.py                     schemas.py    structured output models
db/     models, store, schema.sql (Supabase)      llm.py        provider factory ("provider:model")
tests/ 28 tests, no API key needed                prompts.py    all prompts (versioned)
docs/  you are here                               classifier.py batching + cache + cascade
                                                  apply.py      validated labels -> table
                                                  recommender.py / evaluator.py   LLM #2/#3 + checks
                                                  cost.py, cache.py, estimate.py, classifier_eval.py, run.py, mock.py
```

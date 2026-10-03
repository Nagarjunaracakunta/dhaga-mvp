# 3. LLM usage, model choice and cost

## The three model calls

| # | Purpose | Tier | Input | Output (validated) | Frequency |
|---|---|---|---|---|---|
| 1 | Classify "Other" comments | **Fast/cheap** | Up to 25 comments (text only) per call | `BatchOutput`: per id `primary_reason`, `sub_reason`, `body_area`, `confidence` | Once per *new unique* comment |
| 1b | Re-classify unsure items | **Strong** | Only items with confidence < 0.6 (capped at 20% of the batch) | same schema | Rare |
| 2 | Write investigation brief | **Strong** | Pre-computed evidence JSON for one insight | `Recommendation`: headline, explanation, suggested_action | Top-K insights only (default 5) x attempts |
| 3 | Fact-check the brief | **Fast/cheap** | Evidence + draft | `Verdict`: passed, issues | Only after code checks pass |

## Cost levers (what actually saves money)

| Lever | Where | Effect |
|---|---|---|
| Only "Other" + comment goes to a model | `backend/normalization.py` | ~56% of returns and all blank comments never touch an LLM (on the demo data) |
| Drop junk comments ("." etc.) | `ai/classifier.py` | Zero-cost handling of non-information |
| **Dedupe** identical comments | `ai/classifier.py` | Each distinct comment classified once per run (inflated on synthetic data, smaller on real data) |
| **Persistent cache** (SQLite) | `ai/cache.py` | Re-runs and new data only pay for *new* comments; key = prompt version + model + comment |
| **Batching** 25 comments/call | `ai/config.BATCH_SIZE` | The ~420-token system prompt + examples is paid once per 25 comments instead of per comment |
| **Cheap model by default**, escalate only when unsure | cascade | Strong-model tokens spent on ~10% of items rather than 100% |
| Insight-first recommending | `ai/run.py` | Strong model sees ~5 small evidence objects, never raw rows |
| Free checks before the LLM judge | `ai/evaluator.py` | Judge call only when code checks already pass |
| Hard budget guards | `ai/cost.py` | `--max-usd` / `--max-calls`; run stops cleanly and reports what was skipped |
| `--limit N` | `ai/run.py` | Cheap first real run on N unique comments |

Check before spending: `python -m ai.estimate` prints calls and USD for your configured models, versus a naive
"one strong-model call per row" baseline. On the demo data it estimates roughly an order of magnitude or more of saving, but
**most of that comes from synthetic data having few distinct comments**; real data will save less from dedupe and more
from batching and the cheap model. After a real run, trust `ai_run_report.json` (actual token usage), not the estimate.

> Prices in `ai/config.py` are budgeting estimates. Verify them against each provider's pricing page; unknown models are counted as $0 and listed under `unpriced_models` in the report.

## Temperatures (stated on purpose)
| Step | Temperature | Why |
|---|---|---|
| Comment classification | 0.0 | Extraction must be repeatable; the same comment should get the same label |
| Fact-check judge | 0.0 | Evaluation must be repeatable |
| Brief writer | 0.3 | Internal text; a little variance lets a regeneration after failed checks differ from the previous attempt |
Nothing here is customer-facing. Anything customer-facing later (e.g. listing copy) would get its own, higher, stated setting plus a human review step.

## Cost line at Dhaga's volume (`python -m ai.estimate --weekly`)
```
orders per week                         48,000   [brief]
x return rate 31%                       = 14,880 returns/week   [brief]
x 'Other' share 44%                     = 6,547 'Other' returns/week   [brief]
x with a comment 90%                    = 5,892 comments/week   [assumed]
x unique 70% (dedupe, real text)         = 4,125 to classify/week   [assumed]
/ 25 per call                         = 165 fast-model calls; ~18 tokens/comment (measured on demo text), 421 system tokens/call
classification (openrouter:anthropic/claude-haiku-4.5)   = $0.723
escalation 10% to openrouter:openai/gpt-4o = $0.152   [assumed rate]
5 briefs x 1.5 attempts (writer + judge)   = $0.039   [assumed tokens]
ONE WEEKLY RUN                           = $0.91  = Rs 80   (at Rs 88/USD [assumed])
per 1,000 'Other' returns                = $0.140
per year (x52)                           = $48  = Rs 4,181
naive baseline (1 strong call per row)   = $9.02/week  (10x more)
prices are budgeting estimates from ai/config.py - verify before quoting to the client
```
**[brief]** numbers come from the case study; **[assumed]** ones are ours and are flags on the command (`--comment-rate`, `--unique-ratio`, `--usd-inr`).
Add `--fast ... --strong ...` to price another model pair. Measure one real run (`ai_run_report.json`) and replace the assumed token counts with actuals before presenting.

## Supporting two (or more) models
A model is a string `provider:model`. **OpenRouter is the default provider**: one key (`OPENROUTER_API_KEY`) reaches several vendors,
so the defaults already use two different models:

```
LLM_FAST=openrouter:anthropic/claude-haiku-4.5      # bulk classification, judge
LLM_STRONG=openrouter:openai/gpt-4o                 # escalations, brief writing
LLM_FALLBACK=openrouter:openai/gpt-4o-mini          # optional: used automatically if the fast model errors
```
Other providers are opt-in and each needs its own key: `--provider anthropic` (`ANTHROPIC_API_KEY`) or `--provider openai` (`OPENAI_API_KEY`);
mixed setups also work. Via OpenRouter, structured output uses tool calling, so the chosen model must support it; check `--limit 30 --eval` first.
Adding a provider = one branch in `ai/llm.py::get_chat_model` (+ its LangChain package and a price row). The cache key includes the model,
so switching models re-classifies instead of reusing another model's answers, which makes **A/B comparison of models** a two-command job.

## Quality evaluation
- `python -m ai.run --eval` compares LLM labels with `data/returns_ground_truth.csv` (demo data only): accuracy overall, accuracy on trusted
  (above-threshold) rows, trusted share, body-area accuracy and the top confusions.
- The offline `mock` provider scores near 100% because its keyword rules were written against the same templates; **it validates plumbing, not accuracy**.
- For real data: hand-label ~200 random "Other" comments, put them in the same CSV format, run `--eval` for each candidate model, and choose
  the cheapest model that meets the agreed accuracy bar. Tune `CONFIDENCE_THRESHOLD` on that sample.

## Safety and privacy
- Step 1 sends **only comment text** (no customer id, order id or name); free text can still contain personal details, so check
  the provider's data-handling terms before sending real data.
- Temperature is 0 for repeatability. Prompts live in `ai/prompts.py`; change them -> bump `PROMPT_VERSION` so stale cache entries are ignored.

## Known limitations
- Real provider calls were **not executed during development** (no API keys in the build environment). Chain construction,
  schemas, batching, retries, cache, budget and evaluator logic are covered by tests using the mock provider; do a small real run
  (`python -m ai.run --limit 30 --eval`) and inspect `ai_run_report.json` before scaling up.
- Devanagari-script comments and very long comments were not specifically tested.
- Token usage with a fallback provider is attributed to the primary model in the cost report (approximation).
- Taxonomy is a proposal and will evolve; changing it requires a `PROMPT_VERSION` bump.
- Not yet built: reviewer UI, prompt caching of the system prompt (a further saving at large volume), a drift monitor.

# 1. The problem we are solving

> The one-page discovery note (ranked shortlist, assumption, citations to the brief) is [00-discovery-note.md](00-discovery-note.md). This page adds constraints and metrics.

## Context
Dhaga (the case-study fashion brand) lets customers return items and pick a reason from a dropdown. If none fits they choose
**"Other"** and type free text. Per the case-study brief, about **44% of returns land in "Other"**. The brand also has **no ML engineer**.

## Why this hurts
- The dropdown answers "what category?" but the *useful* detail (which body area is tight, which colour looked different,
  which fabric complaint) is buried in the free text.
- That text is **messy**: English, Hindi and Hinglish, abbreviations, typos, one-word comments ("ok ok", ".").
- Reading thousands of comments by hand is slow and inconsistent, so nobody can count them. Patterns such as
  *"Floral Midi Dress, sizes M/L, shoulders too tight"* stay invisible while the returns keep happening.

## What we build
A small system that turns raw return data into **a short, ranked list of evidence-backed investigation briefs** for a human reviewer (Neha):

> "Investigate shoulder fit on Floral Midi Dress (size L): 48 of 115 orders returned (41.7%) vs 12.4% overall; fit / too tight is the top reason."

The reviewer approves, edits or dismisses each brief. **The system never takes business actions itself.**

## Non-goals
Automatic refunds/decisions, model training or fine-tuning, real-time scoring, root-causing beyond what the data supports.

## Constraints that shaped the design
| Constraint | Consequence |
|---|---|
| Cost must stay low | LLM only where language understanding is needed; batching, cache, cheap model by default (see doc 3) |
| Reliability | Structured outputs validated in code; failures degrade to "unclear / manual review", never to wrong numbers |
| Numbers must be trustworthy | All counts and rates are computed by code; the LLM only writes about numbers it is given, and code re-checks them |
| No ML engineer | No training, no custom infra: prompts + config + tests; models are swappable by editing an env var |
| Human stays in charge | Every recommendation goes to a reviewer; failures are flagged `needs_manual_review` |

## How we will know it works (success metrics)
1. **Classifier accuracy** vs a hand-labelled sample (target to be agreed with the reviewer; the demo data ships ground truth for development).
2. **Trusted share**: % of "Other" comments classified above the confidence threshold.
3. **Cost** per 1,000 returns (reported on every run) and vs the naive baseline (`python -m ai.estimate`).
4. **Recommendation quality**: % passing automated fact checks, and reviewer accept rate.
5. **Time to insight** for the reviewer versus reading comments manually.

## Assumptions to validate
- The taxonomy (`ai/taxonomy.py`) is our proposal; confirm it with the business owner.
- Demo data is **synthetic**, shaped like the real data; real comments will be messier, so re-measure accuracy on real labelled samples before trusting results.

"""All AI-layer knobs in one place."""
PROMPT_VERSION = "v1"          # bump when prompts/taxonomy change -> invalidates the cache

BATCH_SIZE = 25                # comments per classification call (amortises the system prompt)
CONFIDENCE_THRESHOLD = 0.6     # below this (after escalation) a label is NOT trusted -> UNCLEAR
ESCALATE_BELOW = CONFIDENCE_THRESHOLD   # fast-model answers under this are retried on the strong model
MAX_ESCALATION_SHARE = 0.2     # never escalate more than 20% of unique comments (cost cap)

# Temperatures (stated on purpose): extraction/classification/evaluation must be repeatable -> 0.0.
# The brief writer gets 0.3 so a regeneration after failed checks is not a word-for-word repeat. Nothing here is customer-facing.
TEMP_CLASSIFY = 0.0
TEMP_JUDGE = 0.0
TEMP_WRITER = 0.3

MAX_USD_DEFAULT = 2.0          # hard budget per run (estimated from token usage)
MAX_CALLS_DEFAULT = 500        # hard cap on LLM calls per run

TOP_K_INSIGHTS = 5             # only the top-K candidate insights get a (strong-model) recommendation
MAX_REC_ATTEMPTS = 3           # evaluator-optimizer loop: generate -> check -> regenerate
MAX_EXPLANATION_WORDS = 80

# USD per 1M tokens (input, output). ESTIMATES FOR BUDGETING ONLY - verify against each
# provider's pricing page and edit here. Unknown models are counted as $0 and flagged in the report.
PRICES_PER_MTOK = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5-5": (3.00, 15.00),   # assumed - verify
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # OpenRouter slugs (vendor/model). Token prices are usually passed through; verify on openrouter.ai/models.
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "mock": (0.0, 0.0),
}

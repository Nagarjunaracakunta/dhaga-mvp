"""LLM #1 - batched, cached, cost-guarded comment classifier (cheap model, escalate when unsure)."""
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Optional

from . import config
from .cache import ClassificationCache, cache_key
from .llm import AuthError, ModelSpec, structured_chain, invoke_tracked
from .mock import mock_classifier
from .prompts import CLASSIFY_PROMPT
from .schemas import BatchOutput
from .taxonomy import is_valid_combo

log = logging.getLogger(__name__)


@dataclass
class Classification:
    primary: str
    sub: str
    body_area: str
    confidence: float
    source: str        # rule | cache | llm | llm_escalated | failed
    model: str = ""


def normalize_comment(c: str) -> str:
    return re.sub(r"\s+", " ", c.strip().lower())


def is_junk(c: str) -> bool:
    """Nothing to understand (e.g. '.', '-', 'ok' < 3 chars): never worth a model call."""
    return len(re.sub(r"[\W_]+", "", c)) < 3


def build_classifier_chain(spec: ModelSpec, fallback: Optional[ModelSpec] = None):
    if spec.provider == "mock":
        return mock_classifier
    return structured_chain(CLASSIFY_PROMPT, BatchOutput, spec, fallback, temperature=config.TEMP_CLASSIFY)


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _call_batch(chain, spec, tracker, texts):
    """-> ({idx: ItemClassification} for valid answers, [idx of missing/invalid])."""
    payload = {"items_json": json.dumps([{"id": i, "comment": t} for i, t in enumerate(texts)], ensure_ascii=False)}
    try:
        parsed = invoke_tracked(chain, payload, spec, tracker)
    except AuthError:
        raise                       # a bad/missing key can never succeed: stop the run, do not mark rows as failed
    except Exception as e:  # network / provider errors must not crash the run
        log.warning("LLM call failed (%s): %s", spec.label, e)
        parsed = None
    ok = {}
    for it in (parsed.items if parsed else []):
        if 0 <= it.id < len(texts) and it.id not in ok and is_valid_combo(it.primary_reason, it.sub_reason):
            it.confidence = min(max(float(it.confidence), 0.0), 1.0)
            ok[it.id] = it
    return ok, [i for i in range(len(texts)) if i not in ok]


def _to_cls(it, source, model):
    return Classification(it.primary_reason.value, it.sub_reason.value, it.body_area.value, it.confidence, source, model)


def classify_comments(comments, fast: ModelSpec, strong: ModelSpec, tracker, cache: Optional[ClassificationCache] = None,
                      batch_size=config.BATCH_SIZE, escalate=True, limit: Optional[int] = None,
                      fast_chain=None, strong_chain=None, fallback: Optional[ModelSpec] = None):
    """comments: list[str] (may contain duplicates). -> (dict[normalized_comment -> Classification], stats Counter).
    Comments missing from the result were not processed (budget/limit) and stay pending."""
    stats = Counter()
    uniq = {}
    for c in comments:
        uniq.setdefault(normalize_comment(c), c.strip())
    stats["rows"], stats["unique_comments"] = len(comments), len(uniq)

    results, todo = {}, []
    for k, text in uniq.items():
        if is_junk(text):
            results[k] = Classification("UNCLEAR", "UNCLEAR", "NONE", 1.0, "rule")
            stats["rule_junk"] += 1
        else:
            todo.append(k)

    if cache and todo:
        keymap = {cache_key(k, fast.label): k for k in todo}
        for ck, val in cache.get_many(list(keymap)).items():
            d = json.loads(val); d["source"] = "cache"
            results[keymap[ck]] = Classification(**d)
        todo = [k for k in todo if k not in results]
        stats["cache_hits"] = len(keymap) - len(todo)

    if limit is not None and len(todo) > limit:
        stats["left_unprocessed_limit"] = len(todo) - limit
        todo = todo[:limit]

    fast_chain = fast_chain or build_classifier_chain(fast, fallback)
    fresh = []
    for chunk in _chunks(todo, batch_size):
        if tracker.over_budget():
            stats["skipped_budget"] += len(chunk)
            continue
        texts = [uniq[k] for k in chunk]
        ok, failed = _call_batch(fast_chain, fast, tracker, texts)
        if failed and not tracker.over_budget():          # one retry for just the missing/invalid items
            ok2, _ = _call_batch(fast_chain, fast, tracker, [texts[i] for i in failed])
            for j, it in ok2.items():
                ok[failed[j]] = it
            stats["batch_retries"] += 1
        for i, k in enumerate(chunk):
            if i in ok:
                results[k] = _to_cls(ok[i], "llm", fast.label)
            else:
                results[k] = Classification("UNCLEAR", "UNCLEAR", "NONE", 0.0, "failed", fast.label)
                stats["failed"] += 1
            fresh.append(k)

    if escalate and fresh:       # cascade: only the unsure ones go to the expensive model
        unsure = sorted((k for k in fresh if results[k].confidence < config.ESCALATE_BELOW),
                        key=lambda k: results[k].confidence)
        unsure = unsure[:math.ceil(config.MAX_ESCALATION_SHARE * len(fresh))]
        strong_chain = strong_chain or build_classifier_chain(strong, fallback)
        for chunk in _chunks(unsure, batch_size):
            if tracker.over_budget():
                break
            ok, _ = _call_batch(strong_chain, strong, tracker, [uniq[k] for k in chunk])
            for i, it in ok.items():
                results[chunk[i]] = _to_cls(it, "llm_escalated", strong.label)
                stats["escalated"] += 1

    if cache:
        rows = {cache_key(k, fast.label): json.dumps(asdict(results[k]))
                for k in fresh if results[k].source in ("llm", "llm_escalated")}
        if rows:
            cache.put_many(rows)
    stats["classified_by_llm"] = sum(1 for k in fresh if results[k].source in ("llm", "llm_escalated"))
    return results, stats

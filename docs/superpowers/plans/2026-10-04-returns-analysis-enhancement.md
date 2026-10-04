# Returns Analysis Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add model-escalation routing, LLM investigation briefs (evaluator-optimizer), a richer classify prompt, and insight-level human review to main's returns analysis, surfaced in the React UI.

**Architecture:** Port PR 3's routing + evaluator-optimizer patterns onto main's `backend/modules/returns/` (FastAPI + Supabase) and `frontend/src/pages/Returns.jsx` (React). A new `briefs.py` module writes and self-checks briefs; a new `returns_briefs` Supabase table persists them; new router endpoints and `api.js` methods expose them.

**Tech Stack:** Python 3 / FastAPI / pandas / Pydantic / the repo's `backend/shared/llm.py` LLM protocol (Anthropic + OpenRouter), pytest + `FakeLLM`; React (Vite) frontend; Supabase Postgres.

**Spec:** `docs/superpowers/specs/2026-10-04-returns-analysis-enhancement-design.md`

## Global Constraints

- **Strong model:** `settings.model_strong` = `"claude-sonnet-5-5"` for escalation + brief writing. Bulk classify + judge use `settings.model_fast` = `"claude-haiku-4-5"`.
- **Temperatures:** classify/escalate/judge at `0`; brief writer at `0.3`. Pass `temperature=0` explicitly (Sonnet accepts it).
- **LLM errors are returned inline**, never raised, by `parse_many`; each element is an `LLMResult` or an exception (`LLMUnavailable` / `LLMOutputError`). Always `isinstance`-check.
- **Fail visibly:** an LLM failure never crashes an endpoint; it degrades to the fast result (escalation) or `status="needs_manual_review"` (briefs), carried to the UI.
- **No new taxonomy enums**, no per-return model column, no CX changes.
- **Tests use `FakeLLM`** (see `tests/returns/test_classifier.py`) — free, deterministic. Never call a live model in tests.
- **Commit after every task.** Attribution footer on commits: `Co-Authored-By: Claude <noreply@anthropic.com>`.

---

### Task 1: Escalation config + routing in the classifier

**Files:**
- Modify: `backend/modules/returns/config.py` (append thresholds)
- Modify: `backend/modules/returns/classifier.py` (`classify_comments`)
- Test: `tests/returns/test_classifier.py` (append)

**Interfaces:**
- Consumes: `parse_many(llm, *, model, system, users, output_format, max_tokens, temperature, max_concurrency) -> list[LLMResult|Exception]`; `ReturnClassification` (existing); `Settings.model_fast`, `Settings.model_strong`.
- Produces: `classify_comments(...)` return dict unchanged keys plus `"escalated": int` and `"strong_model": str`.

- [ ] **Step 1: Add config thresholds**

In `backend/modules/returns/config.py`, append under the `# ---- Insight thresholds ----` block:

```python
# ---- Classifier escalation (routing) ----
ESCALATE_BELOW = 0.70          # fast-model confidence under this is retried on the strong model
MAX_ESCALATION_SHARE = 0.20    # never escalate more than 20% of the comments in one run (cost cap)
```

- [ ] **Step 2: Write the failing test**

Append to `tests/returns/test_classifier.py`:

```python
def low(conf=0.4):
    return classifier.ReturnClassification(category="FIT", sub_reason="NONE", body_area="NONE", confidence=conf)


def test_low_confidence_is_escalated_to_the_strong_model_capped_at_20pct():
    # 10 comments: first 5 come back low-confidence on the fast model, rest are confident.
    def fn(user):
        return low() if "escalate" in user else fit()
    llm = FakeLLM(fn)
    comments = {f"r{i}": ("escalate me" if i < 5 else "fits fine") for i in range(10)}
    run = classifier.classify_comments(llm, settings(), comments)
    strong_calls = [c for c in llm.calls if c["model"] == "claude-sonnet-5-5"]
    # cap is 20% of 10 = 2, so only 2 of the 5 low-confidence comments are escalated
    assert run["escalated"] == 2
    assert len(strong_calls) == 2
    assert all(c["temperature"] == 0 for c in strong_calls)
    assert run["strong_model"] == "claude-sonnet-5-5"


def test_escalation_keeps_the_higher_confidence_answer():
    # fast says FIT@0.4; strong says QUALITY@0.9 -> strong wins
    def fn(user):
        return low() if "q" not in user else classifier.ReturnClassification(
            category="QUALITY", sub_reason="FABRIC", body_area="NONE", confidence=0.9)
    # route by model: FakeLLM has no model switch, so encode in a wrapper
    class TwoModel:
        def __init__(self): self.calls = []
        def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None, allow_fallback_model=False):
            self.calls.append({"model": model, "temperature": temperature})
            parsed = (classifier.ReturnClassification(category="QUALITY", sub_reason="FABRIC", body_area="NONE", confidence=0.9)
                      if model == "claude-sonnet-5-5" else low())
            return LLMResult(parsed=parsed, model=model, input_tokens=10, output_tokens=5, cost_usd=0.001, latency_ms=1)
    llm = TwoModel()
    run = classifier.classify_comments(llm, settings(), {"r0": "unclear text"})
    assert run["results"]["r0"]["ai_category"] == "QUALITY"
    assert run["results"]["r0"]["ai_confidence"] == 0.9
    assert run["escalated"] == 1
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/returns/test_classifier.py::test_low_confidence_is_escalated_to_the_strong_model_capped_at_20pct -v`
Expected: FAIL (`KeyError: 'escalated'`).

- [ ] **Step 4: Implement escalation in `classify_comments`**

In `backend/modules/returns/classifier.py`, add imports at top:

```python
from .config import ESCALATE_BELOW, MAX_ESCALATION_SHARE
```

Replace the body of `classify_comments` from the `results, failed, cost = ...` line through the `return {...}` with:

```python
    results, failed, cost = {}, {}, 0.0
    for rid, out in zip(ids, outputs):
        if isinstance(out, LLMUnavailable):
            failed[rid] = f"unavailable: {out}"
        elif isinstance(out, Exception):
            failed[rid] = str(out)
        else:
            c = out.parsed
            c.confidence = min(max(c.confidence, 0.0), 1.0)
            results[rid] = {"ai_category": c.category, "ai_subcategory": subcategory(c),
                            "ai_confidence": round(c.confidence, 4)}
            cost += out.cost_usd

    # Routing: retry the least-confident answers on the stronger model, capped at a share of the run.
    cap = int(len(ids) * MAX_ESCALATION_SHARE)
    uncertain = sorted((rid for rid in results if results[rid]["ai_confidence"] < ESCALATE_BELOW),
                       key=lambda r: results[r]["ai_confidence"])[:cap]
    escalated = 0
    for rid in uncertain:
        out = llm.parse(model=settings.model_strong, system=SYSTEM,
                        user=f"<comment>\n{comments[rid]}\n</comment>",
                        output_format=ReturnClassification, max_tokens=256, temperature=0)
        if isinstance(out, Exception):      # strong model down -> keep the fast answer, stay visible
            continue
        cost += out.cost_usd
        escalated += 1
        c = out.parsed
        c.confidence = min(max(c.confidence, 0.0), 1.0)
        if round(c.confidence, 4) >= results[rid]["ai_confidence"]:
            results[rid] = {"ai_category": c.category, "ai_subcategory": subcategory(c),
                            "ai_confidence": round(c.confidence, 4)}

    return {"results": results, "failed": failed, "cost_usd": round(cost, 6),
            "latency_ms": int((time.perf_counter() - start) * 1000), "model": settings.model_fast,
            "strong_model": settings.model_strong, "escalated": escalated,
            "prompt_version": PROMPT_VERSION}
```

Note: `llm.parse` may raise for a real client; wrap in try/except to honour "fail visibly":

```python
        try:
            out = llm.parse(model=settings.model_strong, system=SYSTEM,
                            user=f"<comment>\n{comments[rid]}\n</comment>",
                            output_format=ReturnClassification, max_tokens=256, temperature=0)
        except Exception:
            continue
```

(Use the try/except form; drop the `isinstance(out, Exception)` guard since a raised error is caught.)

- [ ] **Step 5: Run the new tests + the whole returns suite**

Run: `pytest tests/returns/test_classifier.py -v`
Expected: PASS (including the two existing tests — `escalated` defaults correctly; the all-confident test escalates 0).

- [ ] **Step 6: Commit**

```bash
git add backend/modules/returns/config.py backend/modules/returns/classifier.py tests/returns/test_classifier.py
git commit -m "feat(returns): escalate low-confidence classifications to the strong model"
```

---

### Task 2: Brief schemas, prompts, evidence + deterministic checks

**Files:**
- Create: `backend/modules/returns/briefs.py`
- Create: `backend/modules/returns/prompts/write_brief_v1.md`
- Create: `backend/modules/returns/prompts/judge_brief_v1.md`
- Modify: `backend/modules/returns/config.py` (append brief thresholds)
- Test: `tests/returns/test_briefs.py`

**Interfaces:**
- Consumes: a candidate insight dict (`insight_id, product_name, product_id, orders, returns, return_rate, baseline_rate, lift, reason_breakdown, sample_comments`).
- Produces: `Brief` (pydantic), `Verdict` (pydantic), `build_evidence(insight) -> dict`, `deterministic_checks(brief: Brief, insight: dict) -> list[str]`.

- [ ] **Step 1: Add config thresholds**

Append to `backend/modules/returns/config.py`:

```python
# ---- Brief generation (evaluator-optimizer) ----
TOP_K_BRIEFS = 5          # only the top-K flagged insights get an LLM brief
MAX_BRIEF_ATTEMPTS = 3    # write -> check -> regenerate loop
MAX_BRIEF_WORDS = 80      # explanation length cap (deterministic check)
```

- [ ] **Step 2: Write the prompts**

`backend/modules/returns/prompts/write_brief_v1.md`:

```markdown
You are helping a fashion retail category manager understand why a product segment is being returned.
You are given hard numbers and real customer comments. Write a short investigation brief.

Rules:
- Be specific and use the numbers you are given. Do not invent any number.
- Always name the product.
- `explanation`: at most 80 words, plain language, no jargon.
- `suggested_action`: one concrete next step the category team can take this week.
- If reviewer feedback is provided, fix exactly those issues and keep everything else.

Return JSON matching the schema: headline, explanation, suggested_action.
```

`backend/modules/returns/prompts/judge_brief_v1.md`:

```markdown
You fact-check a short retail returns brief against the evidence JSON.
Fail the brief if: it states a number that contradicts the evidence, names the wrong product,
makes a claim the evidence does not support, or gives no actionable next step.
Return JSON: passed (bool), issues (list of short strings; empty if it passes).
```

- [ ] **Step 3: Write the failing test**

`tests/returns/test_briefs.py`:

```python
from backend.modules.returns import briefs


def insight(**over):
    base = dict(insight_id="product_size:P1|M", product_id="P1", product_name="Floral Midi Dress",
                orders=200, returns=76, return_rate=0.38, baseline_rate=0.18, lift=2.1,
                reason_breakdown={"FIT": 60, "QUALITY": 16}, sample_comments=["shoulders tight", "chest fit nahi hua"])
    base.update(over)
    return base


def test_build_evidence_has_the_numbers_the_brief_must_match():
    ev = briefs.build_evidence(insight())
    assert ev["product_name"] == "Floral Midi Dress"
    assert ev["return_rate_pct"] == 38.0
    assert ev["returns"] == 76 and ev["orders"] == 200
    assert ev["lift"] == 2.1


def test_deterministic_checks_flags_missing_number_and_product():
    good = briefs.Brief(headline="Floral Midi Dress fit problem",
                        explanation="Floral Midi Dress is returned at 38% versus 18% overall, mostly fit.",
                        suggested_action="Re-check the M size chart with the vendor.")
    assert briefs.deterministic_checks(good, insight()) == []

    no_number = briefs.Brief(headline="x", explanation="This dress comes back a lot, mostly fit.",
                             suggested_action="Check it.")
    issues = briefs.deterministic_checks(no_number, insight())
    assert any("number" in i.lower() or "rate" in i.lower() for i in issues)

    no_product = briefs.Brief(headline="x", explanation="Returned at 38% versus 18% overall.",
                              suggested_action="Check it.")
    assert any("product" in i.lower() for i in briefs.deterministic_checks(no_product, insight()))

    too_long = briefs.Brief(headline="x", suggested_action="Act.",
                            explanation="Floral Midi Dress 38% " + "word " * 90)
    assert any("word" in i.lower() or "long" in i.lower() for i in briefs.deterministic_checks(too_long, insight()))
```

- [ ] **Step 4: Run to verify it fails**

Run: `pytest tests/returns/test_briefs.py -v`
Expected: FAIL (`ModuleNotFoundError: backend.modules.returns.briefs`).

- [ ] **Step 5: Implement `briefs.py` (schemas, evidence, checks)**

Create `backend/modules/returns/briefs.py`:

```python
"""Evaluator-optimizer: an LLM writes an investigation brief per flagged insight; a second
model fact-checks it against the numbers; it loops until it passes or is flagged for a human.

Writer = Sonnet 5.5 (temp 0.3). Judge = Haiku 4.5 (temp 0). All arithmetic is done in code
here (build_evidence); the models only get judgment and language.
"""
import time
from pathlib import Path

from pydantic import BaseModel, Field

from backend.shared.llm import LLM
from backend.shared.settings import Settings
from .config import MAX_BRIEF_ATTEMPTS, MAX_BRIEF_WORDS

WRITE_VERSION = "write_brief_v1"
JUDGE_VERSION = "judge_brief_v1"
WRITE_SYSTEM = (Path(__file__).parent / "prompts" / f"{WRITE_VERSION}.md").read_text()
JUDGE_SYSTEM = (Path(__file__).parent / "prompts" / f"{JUDGE_VERSION}.md").read_text()


class Brief(BaseModel):
    headline: str
    explanation: str = Field(description="<= 80 words, plain language")
    suggested_action: str


class Verdict(BaseModel):
    passed: bool
    issues: list[str] = []


def build_evidence(insight: dict) -> dict:
    """The hard numbers the brief must be true to. Pure code."""
    return {
        "insight_id": insight["insight_id"],
        "product_name": insight["product_name"],
        "segment": insight.get("segment") or {},
        "orders": insight["orders"],
        "returns": insight["returns"],
        "return_rate_pct": round(insight["return_rate"] * 100, 1),
        "baseline_rate_pct": round(insight["baseline_rate"] * 100, 1),
        "lift": insight["lift"],
        "reason_breakdown": insight.get("reason_breakdown") or {},
        "sample_comments": (insight.get("sample_comments") or [])[:5],
    }


def deterministic_checks(brief: Brief, insight: dict) -> list[str]:
    """Free, exact checks before spending a judge call."""
    ev = build_evidence(insight)
    issues: list[str] = []
    text = f"{brief.headline} {brief.explanation}".lower()
    if ev["product_name"].lower() not in text:
        issues.append("Brief does not name the product.")
    rate = str(ev["return_rate_pct"])
    if rate not in brief.explanation and str(int(ev["return_rate_pct"])) not in brief.explanation \
            and str(ev["returns"]) not in brief.explanation:
        issues.append("Explanation cites no return-rate number from the evidence.")
    if len(brief.explanation.split()) > MAX_BRIEF_WORDS:
        issues.append(f"Explanation is longer than {MAX_BRIEF_WORDS} words.")
    if not brief.suggested_action.strip():
        issues.append("No suggested action.")
    return issues
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/returns/test_briefs.py -v`
Expected: PASS (all four assertions in the two tests).

- [ ] **Step 7: Commit**

```bash
git add backend/modules/returns/briefs.py backend/modules/returns/prompts/write_brief_v1.md backend/modules/returns/prompts/judge_brief_v1.md backend/modules/returns/config.py tests/returns/test_briefs.py
git commit -m "feat(returns): brief schemas, prompts, evidence and deterministic checks"
```

---

### Task 3: The `generate_brief` evaluator-optimizer loop

**Files:**
- Modify: `backend/modules/returns/briefs.py` (add `generate_brief`)
- Test: `tests/returns/test_briefs.py` (append)

**Interfaces:**
- Consumes: `LLM.parse(...)`, `Settings.model_fast`, `Settings.model_strong`, `Brief`, `Verdict`, `build_evidence`, `deterministic_checks`.
- Produces: `generate_brief(llm, settings, insight) -> dict` with keys `insight_id, product_id, product_name, brief (dict), status, open_issues (list[str]), attempts, model, cost_usd, latency_ms`.

- [ ] **Step 1: Write the failing test**

Append to `tests/returns/test_briefs.py`:

```python
import json
from backend.shared.llm import LLMResult, LLMUnavailable
from backend.shared.settings import Settings


def settings():
    return Settings(_env_file=None, supabase_url="", supabase_service_key="", anthropic_api_key="", openrouter_api_key="")


class ScriptLLM:
    """Returns a queued object per call; records models used."""
    def __init__(self, script):
        self.script, self.i, self.calls = script, 0, []
    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None, allow_fallback_model=False):
        self.calls.append({"model": model, "temperature": temperature})
        out = self.script[self.i]; self.i += 1
        if isinstance(out, Exception):
            raise out
        return LLMResult(parsed=out, model=model, input_tokens=200, output_tokens=40, cost_usd=0.002, latency_ms=5)


def good_brief():
    return briefs.Brief(headline="Floral Midi Dress fit",
                        explanation="Floral Midi Dress returns at 38% vs 18% overall, mostly fit.",
                        suggested_action="Re-check the M size chart.")


def test_generate_brief_passes_on_a_clean_first_draft():
    llm = ScriptLLM([good_brief(), briefs.Verdict(passed=True, issues=[])])
    out = briefs.generate_brief(llm, settings(), insight())
    assert out["status"] == "passed_checks" and out["attempts"] == 1
    assert out["brief"]["headline"] == "Floral Midi Dress fit"
    assert [c["model"] for c in llm.calls] == ["claude-sonnet-5-5", "claude-haiku-4-5"]
    assert llm.calls[0]["temperature"] == 0.3 and llm.calls[1]["temperature"] == 0


def test_generate_brief_regenerates_after_a_judge_rejection():
    llm = ScriptLLM([good_brief(), briefs.Verdict(passed=False, issues=["too vague"]),
                     good_brief(), briefs.Verdict(passed=True, issues=[])])
    out = briefs.generate_brief(llm, settings(), insight())
    assert out["attempts"] == 2 and out["status"] == "passed_checks"


def test_generate_brief_flags_manual_review_when_it_never_passes():
    llm = ScriptLLM([good_brief(), briefs.Verdict(passed=False, issues=["bad"])] * 3)
    out = briefs.generate_brief(llm, settings(), insight())
    assert out["status"] == "needs_manual_review"
    assert out["attempts"] == 3 and out["open_issues"]


def test_generate_brief_handles_a_dead_model_visibly():
    out = briefs.generate_brief(ScriptLLM([LLMUnavailable("down")]), settings(), insight())
    assert out["status"] == "needs_manual_review"
    assert any("unavailable" in i.lower() or "down" in i.lower() for i in out["open_issues"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/returns/test_briefs.py::test_generate_brief_passes_on_a_clean_first_draft -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'generate_brief'`).

- [ ] **Step 3: Implement `generate_brief`**

Append to `backend/modules/returns/briefs.py`:

```python
def generate_brief(llm: LLM, settings: Settings, insight: dict) -> dict:
    ev = build_evidence(insight)
    evidence_json = __import__("json").dumps(ev, ensure_ascii=False)
    cost, feedback, open_issues = 0.0, "", []
    start = time.perf_counter()
    brief = None
    for attempt in range(1, MAX_BRIEF_ATTEMPTS + 1):
        user = f"<evidence>\n{evidence_json}\n</evidence>"
        if feedback:
            user += f"\n<reviewer_feedback>\n{feedback}\n</reviewer_feedback>"
        try:
            w = llm.parse(model=settings.model_strong, system=WRITE_SYSTEM, user=user,
                          output_format=Brief, max_tokens=400, temperature=0.3)
        except Exception as e:
            return _manual(insight, {}, [f"writer unavailable: {e}"], attempt, cost, start, settings)
        cost += w.cost_usd
        brief = w.parsed

        issues = deterministic_checks(brief, insight)
        if issues:
            open_issues, feedback = issues, "; ".join(issues)
            continue

        try:
            v = llm.parse(model=settings.model_fast, system=JUDGE_SYSTEM,
                          user=f"<evidence>\n{evidence_json}\n</evidence>\n<brief>\n{brief.model_dump_json()}\n</brief>",
                          output_format=Verdict, max_tokens=256, temperature=0)
        except Exception as e:
            return _manual(insight, brief.model_dump(), [f"judge unavailable: {e}"], attempt, cost, start, settings)
        cost += v.cost_usd
        if v.passed:
            return _result(insight, brief.model_dump(), "passed_checks", [], attempt, cost, start, settings)
        open_issues, feedback = v.issues, "; ".join(v.issues)

    return _manual(insight, brief.model_dump() if brief else {}, open_issues, MAX_BRIEF_ATTEMPTS, cost, start, settings)


def _result(insight, brief, status, issues, attempts, cost, start, settings):
    return {"insight_id": insight["insight_id"], "product_id": insight.get("product_id"),
            "product_name": insight["product_name"], "brief": brief, "status": status,
            "open_issues": issues, "attempts": attempts, "model": settings.model_strong,
            "cost_usd": round(cost, 6), "latency_ms": int((time.perf_counter() - start) * 1000)}


def _manual(insight, brief, issues, attempts, cost, start, settings):
    return _result(insight, brief, "needs_manual_review", issues, attempts, cost, start, settings)
```

Replace the `__import__("json")` line by adding `import json` to the top of the file and using `json.dumps(...)` (the `__import__` form is only to keep this diff self-contained; prefer the clean import).

- [ ] **Step 4: Run the brief tests**

Run: `pytest tests/returns/test_briefs.py -v`
Expected: PASS (all tests, including the four loop tests).

- [ ] **Step 5: Commit**

```bash
git add backend/modules/returns/briefs.py tests/returns/test_briefs.py
git commit -m "feat(returns): evaluator-optimizer loop to write and fact-check briefs"
```

---

### Task 4: Persist briefs — `returns_briefs` table + store methods

**Files:**
- Create: `db/returns_tables.sql`
- Modify: `backend/modules/returns/store.py` (both stores)
- Test: `tests/returns/test_briefs_store.py`

**Interfaces:**
- Consumes: `get_supabase()` (existing), a brief record from `generate_brief`.
- Produces, on `MemoryStore` and `SupabaseStore`: `save_brief(record: dict) -> None`, `get_briefs() -> list[dict]`, `set_brief_review(insight_id: str, status: str, reviewer: str|None, note: str|None) -> None`.

- [ ] **Step 1: Write the SQL**

Create `db/returns_tables.sql`:

```sql
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
```

- [ ] **Step 2: Write the failing test (MemoryStore only — no network)**

`tests/returns/test_briefs_store.py`:

```python
from backend.modules.returns.store import MemoryStore


def record(iid="product_size:P1|M"):
    return {"insight_id": iid, "product_id": "P1", "product_name": "Floral Midi Dress",
            "brief": {"headline": "h", "explanation": "e", "suggested_action": "a"},
            "status": "passed_checks", "open_issues": [], "attempts": 1,
            "model": "claude-sonnet-5-5", "cost_usd": 0.004}


def test_memory_store_saves_and_lists_briefs():
    s = MemoryStore()
    s.save_brief(record())
    got = s.get_briefs()
    assert len(got) == 1 and got[0]["insight_id"] == "product_size:P1|M"
    assert got[0]["review_status"] == "pending"


def test_memory_store_save_brief_is_idempotent_on_insight_id():
    s = MemoryStore()
    s.save_brief(record()); s.save_brief({**record(), "status": "needs_manual_review"})
    assert len(s.get_briefs()) == 1 and s.get_briefs()[0]["status"] == "needs_manual_review"


def test_memory_store_review_updates_status_and_note():
    s = MemoryStore()
    s.save_brief(record())
    s.set_brief_review("product_size:P1|M", "approved", "neha", "check vendor size chart")
    b = s.get_briefs()[0]
    assert (b["review_status"], b["reviewer"], b["review_note"]) == ("approved", "neha", "check vendor size chart")
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/returns/test_briefs_store.py -v`
Expected: FAIL (`AttributeError: 'MemoryStore' object has no attribute 'save_brief'`).

- [ ] **Step 4: Implement store methods**

In `backend/modules/returns/store.py`, add to `MemoryStore.__init__`:

```python
        self.briefs: dict[str, dict] = {}
```

Add these methods to `MemoryStore`:

```python
    def save_brief(self, record: dict) -> None:
        iid = record["insight_id"]
        existing = self.briefs.get(iid, {"review_status": "pending", "reviewer": None, "review_note": None})
        self.briefs[iid] = {**existing, **record}

    def get_briefs(self) -> list[dict]:
        return list(self.briefs.values())

    def set_brief_review(self, insight_id, status, reviewer=None, note=None) -> None:
        self.briefs.setdefault(insight_id, {"insight_id": insight_id})
        self.briefs[insight_id].update(review_status=status, reviewer=reviewer, review_note=note)
```

Add these methods to `SupabaseStore`:

```python
    def save_brief(self, record: dict) -> None:
        get_supabase().table("returns_briefs").upsert(record, on_conflict="insight_id").execute()

    def get_briefs(self) -> list[dict]:
        return get_supabase().table("returns_briefs").select("*").execute().data or []

    def set_brief_review(self, insight_id, status, reviewer=None, note=None) -> None:
        get_supabase().table("returns_briefs").update(
            {"review_status": status, "reviewer": reviewer, "review_note": note,
             "reviewed_at": "now()"}).eq("insight_id", insight_id).execute()
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/returns/test_briefs_store.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add db/returns_tables.sql backend/modules/returns/store.py tests/returns/test_briefs_store.py
git commit -m "feat(returns): persist briefs in returns_briefs (Supabase + memory)"
```

---

### Task 5: Router endpoints for briefs + escalation in `/classify`

**Files:**
- Modify: `backend/modules/returns/router.py`
- Test: `tests/returns/test_briefs_api.py`

**Interfaces:**
- Consumes: `_result()` (pipeline result, has `candidate_insights`), `get_store()`, `briefs.generate_brief`, `get_llm`, `get_settings`, `config.TOP_K_BRIEFS`.
- Produces endpoints: `POST /api/returns/briefs` `{top_k?: int, redo?: bool}`; `GET /api/returns/briefs`; `POST /api/returns/briefs/{insight_id}/review` `{status, reviewer?, note?}`; `/classify` response gains `escalated`.

- [ ] **Step 1: Write the failing test**

`tests/returns/test_briefs_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.returns import briefs, router as returns_router
from backend.modules.returns.store import MemoryStore
from backend.shared.llm import LLMResult


class ScriptLLM:
    def __init__(self, script): self.script, self.i = script, 0
    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None, allow_fallback_model=False):
        out = self.script[self.i % len(self.script)]; self.i += 1
        return LLMResult(parsed=out, model=model, input_tokens=100, output_tokens=20, cost_usd=0.001, latency_ms=2)


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(returns_router, "get_store", lambda: store)
    good = briefs.Brief(headline="Floral Midi Dress fit",
                        explanation="Floral Midi Dress returns at high rate vs overall, mostly fit.",
                        suggested_action="Re-check the M size chart.")
    monkeypatch.setattr(returns_router, "get_llm", lambda: ScriptLLM([good, briefs.Verdict(passed=True, issues=[])]))
    returns_router._cache.clear()
    return store


def test_generate_then_list_briefs():
    c = TestClient(app)
    gen = c.post("/api/returns/briefs", json={"top_k": 2})
    assert gen.status_code == 200 and gen.json()["generated"] >= 1
    lst = c.get("/api/returns/briefs")
    assert lst.status_code == 200 and len(lst.json()) >= 1
    assert lst.json()[0]["review_status"] == "pending"


def test_review_a_brief():
    c = TestClient(app)
    c.post("/api/returns/briefs", json={"top_k": 1})
    iid = c.get("/api/returns/briefs").json()[0]["insight_id"]
    r = c.post(f"/api/returns/briefs/{iid}/review", json={"status": "approved", "reviewer": "neha"})
    assert r.status_code == 200
    assert c.get("/api/returns/briefs").json()[0]["review_status"] == "approved"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/returns/test_briefs_api.py -v`
Expected: FAIL (404 — endpoints not defined).

- [ ] **Step 3: Implement the endpoints**

In `backend/modules/returns/router.py`, add imports:

```python
from . import aggregation, briefs, classifier
from .config import TOP_K_BRIEFS
```

(extend the existing `from . import aggregation, classifier` line to include `briefs`).

Add before the Stage-2 classify section:

```python
# ---------------- Stage 3: LLM investigation briefs (evaluator-optimizer) ----------------
class BriefRequest(BaseModel):
    top_k: int = TOP_K_BRIEFS
    redo: bool = False


@router.post("/briefs")
def generate_briefs(body: BriefRequest = BriefRequest()):
    """Write + fact-check a brief for each of the top-K flagged insights, and save them."""
    store = get_store()
    insights = _result(refresh=True).candidate_insights[: body.top_k]
    if not insights:
        return {"generated": 0, "message": "No flagged insights to brief."}
    existing = {b["insight_id"] for b in store.get_briefs()} if not body.redo else set()
    generated, cost, manual = 0, 0.0, 0
    for ins in insights:
        if ins["insight_id"] in existing:
            continue
        out = briefs.generate_brief(get_llm(), get_settings(), ins)
        store.save_brief(out)
        store.log_run({"model_name": out["model"], "prompt_version": briefs.WRITE_VERSION,
                       "input_summary": f"brief for {ins['insight_id']}",
                       "output": {"status": out["status"], "attempts": out["attempts"], "cost_usd": out["cost_usd"]},
                       "evaluation_status": "PASSED" if out["status"] == "passed_checks" else "REVIEW_REQUIRED",
                       "processing_time_ms": out["latency_ms"]})
        generated += 1
        cost += out["cost_usd"]
        manual += out["status"] == "needs_manual_review"
    return {"generated": generated, "needs_manual_review": manual, "cost_usd": round(cost, 6)}


@router.get("/briefs")
def list_briefs():
    """Persisted briefs, enriched with current evidence; marked stale if no longer flagged."""
    live = {i["insight_id"]: i for i in _result().candidate_insights}
    out = []
    for b in sorted(get_store().get_briefs(), key=lambda b: live.get(b["insight_id"], {}).get("lift", 0), reverse=True):
        ins = live.get(b["insight_id"])
        out.append({**b, "stale": ins is None, "evidence": briefs.build_evidence(ins) if ins else None})
    return out


class BriefReviewRequest(BaseModel):
    status: Literal["approved", "needs_followup", "dismissed", "pending"]
    reviewer: Optional[str] = None
    note: Optional[str] = None


@router.post("/briefs/{insight_id:path}/review")
def review_brief(insight_id: str, body: BriefReviewRequest):
    get_store().set_brief_review(insight_id, body.status, body.reviewer, body.note)
    return {"insight_id": insight_id, "review_status": body.status}
```

(The `{insight_id:path}` converter is required because `insight_id` contains `|` and `:`.)

In the existing `classify` endpoint's return dict, add `"escalated": run.get("escalated", 0)` and include it in the `log_run` `output`.

- [ ] **Step 4: Run the API tests + full returns suite**

Run: `pytest tests/returns/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/modules/returns/router.py tests/returns/test_briefs_api.py
git commit -m "feat(returns): /briefs generate, list and review endpoints; escalated in /classify"
```

---

### Task 6: Classifier prompt v2 (depth)

**Files:**
- Create: `backend/modules/returns/prompts/classify_return_v2.md`
- Modify: `backend/modules/returns/classifier.py` (`PROMPT_VERSION`)
- Test: run `evals/returns_eval.py` if a labelled set is wired; otherwise a smoke assert.

**Interfaces:**
- Consumes: nothing new. Produces: `PROMPT_VERSION = "classify_return_v2"`.

- [ ] **Step 1: Write v2 prompt**

Create `backend/modules/returns/prompts/classify_return_v2.md` starting from the v1 text (`git show HEAD:backend/modules/returns/prompts/classify_return_v1.md`) and add, without changing the output schema or the category/sub-reason enums:
- 6–8 worked Hinglish/vernacular examples mapping to the correct category + sub_reason + body_area (e.g. "kapda patla hai" → QUALITY/FABRIC; "kandhe pe tight" → FIT/TOO_TIGHT:SHOULDERS; "photo se alag colour" → COLOUR/LISTING_DIFFERENCE; "galat item aaya" → WRONG_ITEM; "mujhe pasand nahi aaya" → CHANGED_MIND; "ok ok" → UNCLEAR low confidence).
- An explicit instruction: when the comment is vague or just acknowledgement ("ok", "theek hai", "nice"), return `UNCLEAR` with confidence < 0.5.
- An instruction to set `body_area` only when the comment names a body region.

- [ ] **Step 2: Point the classifier at v2**

In `backend/modules/returns/classifier.py` change:

```python
PROMPT_VERSION = "classify_return_v2"
```

- [ ] **Step 3: Verify the prompt file loads and the suite still passes**

Run: `pytest tests/returns/ -v`
Expected: PASS (the `SYSTEM` read now points at v2; FakeLLM tests are prompt-agnostic).

- [ ] **Step 4: (If a labelled eval exists) run it both ways and record the number**

Run: `python evals/returns_eval.py` (needs a live key; optional, do once).
Record the accuracy before/after v2 in the commit message. If no key, note "eval not run (no key)".

- [ ] **Step 5: Commit**

```bash
git add backend/modules/returns/prompts/classify_return_v2.md backend/modules/returns/classifier.py
git commit -m "feat(returns): richer Hinglish classify prompt (v2)"
```

---

### Task 7: Frontend API client methods

**Files:**
- Modify: `frontend/src/api.js`

**Interfaces:**
- Produces on the `api` object: `returnsBriefs()`, `returnsGenerateBriefs({topK})`, `returnsBriefReview(insightId, status, note)`.

- [ ] **Step 1: Read the existing client shape**

Run: `sed -n '1,80p' frontend/src/api.js` — match the existing GET/POST helper style and the `BASE`/`request` pattern.

- [ ] **Step 2: Add the three methods**

Following the existing style (adjust names to the real helper, e.g. `get`/`post`), add inside the `api` object:

```js
  returnsBriefs: () => get("/api/returns/briefs"),
  returnsGenerateBriefs: ({ topK = 5 } = {}) => post("/api/returns/briefs", { top_k: topK }),
  returnsBriefReview: (insightId, status, note) =>
    post(`/api/returns/briefs/${encodeURIComponent(insightId)}/review`, { status, reviewer: "neha", note }),
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds (no syntax error).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(returns-ui): api client methods for briefs"
```

---

### Task 8: Frontend "Investigation briefs" panel + review

**Files:**
- Modify: `frontend/src/pages/Returns.jsx`

**Interfaces:**
- Consumes: `api.returnsBriefs`, `api.returnsGenerateBriefs`, `api.returnsBriefReview`, the `useApi` hook, the existing `<ReviewControls>` / `<Stat>` / `<Panel>` components and `CATEGORIES`.

- [ ] **Step 1: Load briefs**

Add near the other `useApi` calls:

```jsx
const briefs = useApi(() => api.returnsBriefs(), []);
```

Add a severity helper near the top of the module:

```jsx
const severity = (lift) => (lift >= 2 ? "High" : lift >= 1.6 ? "Medium" : "Low");
const SEV_COLOR = { High: "#d03b3b", Medium: "#ec835a", Low: "#fab219" };
```

- [ ] **Step 2: Render the panel**

Add a new panel above or below the Flagged-segments panel (match the file's existing `<Panel>`/`<section>` idiom):

```jsx
<Panel title="Investigation briefs">
  <button onClick={async () => { await api.returnsGenerateBriefs({ topK: 5 }); briefs.reload(); }}>
    Generate briefs for the top flagged segments
  </button>
  {briefs.loading && <p>Loading…</p>}
  {briefs.error && <p className="error">Could not load briefs: {String(briefs.error)}</p>}
  {(briefs.data || []).map((b) => {
    const lift = b.evidence?.lift ?? 0;
    const sev = severity(lift);
    return (
      <article key={b.insight_id} className="brief-card" style={{ borderLeft: `5px solid ${SEV_COLOR[sev]}` }}>
        <header>
          <span className="pill" style={{ background: SEV_COLOR[sev] }}>{sev}</span>
          <strong>{b.brief?.headline || b.product_name}</strong>
          {b.stale && <span className="pill stale">stale</span>}
        </header>
        {b.status === "needs_manual_review" && (
          <p className="error">Did not pass the automated fact check — read the numbers yourself: {(b.open_issues || []).join("; ")}</p>
        )}
        <p>{b.brief?.explanation}</p>
        <p><em>Suggested next step:</em> {b.brief?.suggested_action}</p>
        {b.evidence && (
          <p className="muted">
            {b.evidence.return_rate_pct}% returned · {b.evidence.lift}× average · {b.evidence.returns}/{b.evidence.orders} orders
          </p>
        )}
        <BriefReview insightId={b.insight_id} current={b.review_status}
          onDone={() => briefs.reload()} />
      </article>
    );
  })}
</Panel>
```

- [ ] **Step 3: Add the `BriefReview` control**

Add a small component in the same file (mirror `<ReviewControls>`):

```jsx
function BriefReview({ insightId, current, onDone }) {
  const [status, setStatus] = React.useState(current || "pending");
  const [note, setNote] = React.useState("");
  return (
    <div className="brief-review">
      {["approved", "needs_followup", "dismissed"].map((s) => (
        <label key={s}>
          <input type="radio" name={`r-${insightId}`} checked={status === s} onChange={() => setStatus(s)} /> {s}
        </label>
      ))}
      <input placeholder="note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button onClick={async () => { await api.returnsBriefReview(insightId, status, note); onDone(); }}>Save</button>
      {current && current !== "pending" && <span className="muted">current: {current}</span>}
    </div>
  );
}
```

(If the file does not already `import React`, use the existing hook import style, e.g. `import { useState } from "react"` and adjust.)

- [ ] **Step 4: Build + run and verify by hand**

Run backend: `uvicorn backend.main:app --reload` (set `.env` for a live key + Supabase, or run CSV/memory mode).
Run frontend: `cd frontend && npm run dev`, open http://localhost:5173, go to Returns.
Verify: "Generate briefs" produces ranked cards; a failed brief shows the red banner; choosing a review option + Save persists across a page reload. Confirm there are no console errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Returns.jsx
git commit -m "feat(returns-ui): investigation briefs panel with severity and review"
```

---

### Task 9: Docs, cost line, and the PR

**Files:**
- Modify: `README.md` and/or `docs/` returns section
- Create: `docs/returns-build-note.md` (the two-page build note the brief asks for)

- [ ] **Step 1: Update the returns docs**

Document the new flow (classify → escalate → aggregate → brief → judge → human review), the two-model split and temperatures, the `returns_briefs` table, how to apply `db/returns_tables.sql` in Supabase, and the new endpoints. Add a cost line: one brief ≈ (Sonnet write tokens + Haiku judge tokens) and the weekly projection at ~563 returns / Dhaga volume — show the arithmetic from `settings.price_per_mtok`.

- [ ] **Step 2: Full test pass**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 3: Push and open the PR into the group repo**

```bash
git push -u origin feat/returns-analysis-enhance
gh pr create --repo Nagarjunaracakunta/dhaga-mvp --base main --head tanya732:feat/returns-analysis-enhance \
  --title "Returns: escalation routing + LLM investigation briefs + review" \
  --body "$(cat <<'EOF'
## Summary
- Escalate low-confidence Haiku classifications to Sonnet 5.5 (≤20%, temp 0) before bothering a human
- LLM-written investigation briefs per flagged insight with a deterministic + Haiku-judge fact-check loop (evaluator-optimizer), persisted in a new returns_briefs table
- Richer Hinglish classify prompt (v2)
- Insight-level human review (approve / follow-up / dismiss + note) in the React UI

## Test plan
- [ ] pytest -q (backend)
- [ ] Supabase: apply db/returns_tables.sql
- [ ] Generate briefs in the UI, trip the failure banner, review persists on reload

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

(Confirm with the user before pushing/opening the PR — it is a shared action.)

---

## Self-Review notes

- **Spec coverage:** gap 1 escalation → Task 1; gap 2 briefs → Tasks 2–5, 8; gap 3 depth → Task 6; gap 4 review → Tasks 4,5,8. Supabase table → Task 4. Cost line → Task 9. All covered.
- **Type consistency:** `generate_brief` returns the record shape consumed by `store.save_brief`, `GET /briefs`, and the UI card (`insight_id, product_id, product_name, brief, status, open_issues, attempts, model, cost_usd`), with `review_status/reviewer/review_note` added by the store. `classify_comments` adds `escalated` + `strong_model`, consumed by `/classify`.
- **Known risk:** `review_brief` uses `{insight_id:path}` because IDs contain `|`/`:`; the frontend `encodeURIComponent`s the id. The `set_brief_review` Supabase `"now()"` string may need `datetime.now(timezone.utc).isoformat()` depending on the client — verify against a real Supabase call during Task 8.

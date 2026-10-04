"""Brief generation: evidence + deterministic checks + the evaluator-optimizer loop. Fake models only."""
from backend.modules.returns import briefs
from backend.shared.llm import LLMResult, LLMUnavailable
from backend.shared.settings import Settings


def insight(**over):
    base = dict(insight_id="product_size:P1|M", product_id="P1", product_name="Floral Midi Dress",
                orders=200, returns=76, return_rate=0.38, baseline_rate=0.18, lift=2.1,
                reason_breakdown={"FIT": 60, "QUALITY": 16}, sample_comments=["shoulders tight", "chest fit nahi hua"])
    base.update(over)
    return base


def settings():
    return Settings(_env_file=None, supabase_url="", supabase_service_key="", anthropic_api_key="", openrouter_api_key="")


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


class ScriptLLM:
    """Returns a queued object per call; records models used."""
    def __init__(self, script):
        self.script, self.i, self.calls = script, 0, []

    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None,
              allow_fallback_model=False):
        self.calls.append({"model": model, "temperature": temperature})
        out = self.script[self.i]
        self.i += 1
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

import json
import pandas as pd
import pytest
from ai import config as aic
from ai.apply import apply_classifications
from ai.cache import ClassificationCache
from ai.classifier import classify_comments, is_junk, normalize_comment, Classification
from ai.cost import CostTracker
from ai.evaluator import check_numbers, deterministic_checks
from ai.llm import ModelSpec
from ai.recommender import build_evidence, generate_validated_recommendation
from ai.schemas import Recommendation
from ai.taxonomy import is_valid_combo
from backend.pipeline import run_pipeline
from backend.insights import find_candidate_insights

MOCK = ModelSpec.parse("mock:mock")


def test_modelspec_parse():
    assert ModelSpec.parse("openai:gpt-4o-mini") == ModelSpec("openai", "gpt-4o-mini")
    assert ModelSpec.parse("anthropic:claude-haiku-4-5-20251001").provider == "anthropic"


def test_taxonomy_combos():
    assert is_valid_combo("FIT", "TOO_TIGHT")
    assert not is_valid_combo("FIT", "FABRIC")
    assert not is_valid_combo("NOT_A_REASON", "UNSPECIFIED")


def test_junk_and_normalization():
    assert is_junk(".") and is_junk("ok") and not is_junk("tight")
    assert normalize_comment("  Shoulders   TIGHT ") == "shoulders tight"


def test_dedupe_and_junk_skip_save_calls():
    t = CostTracker()
    comments = ["shoulders tight"] * 30 + ["Shoulders  tight"] * 5 + ["."] * 4 + ["fabric cheap hai"]
    res, stats = classify_comments(comments, MOCK, MOCK, t, escalate=False)
    assert stats["unique_comments"] == 3 and stats["rule_junk"] == 1
    assert t.calls == 1  # one batched call for everything, not 40
    assert res["shoulders tight"].primary == "FIT" and res["fabric cheap hai"].primary == "QUALITY"


def test_cache_prevents_second_call(tmp_path):
    cache = ClassificationCache(tmp_path / "c.sqlite")
    t1, t2 = CostTracker(), CostTracker()
    classify_comments(["waist loose hai"], MOCK, MOCK, t1, cache, escalate=False)
    res, stats = classify_comments(["waist loose hai"], MOCK, MOCK, t2, cache, escalate=False)
    assert t1.calls == 1 and t2.calls == 0 and stats["cache_hits"] == 1
    assert res["waist loose hai"].source == "cache"


def test_budget_guard_stops_calls():
    t = CostTracker(max_calls=0)
    res, stats = classify_comments(["waist loose hai"], MOCK, MOCK, t, escalate=False)
    assert t.calls == 0 and stats["skipped_budget"] == 1 and res == {}


def test_low_confidence_becomes_unclear():
    df = pd.DataFrame({"needs_llm": [True, True], "return_comment": ["a b c", "d e f"], "primary_reason": ["UNCLASSIFIED"] * 2,
                       "sub_reason": [None, None], "body_area": [None, None], "classification_source": ["pending_llm"] * 2})
    results = {"a b c": Classification("FIT", "TOO_TIGHT", "WAIST", 0.9, "llm"),
               "d e f": Classification("FIT", "TOO_TIGHT", "WAIST", 0.4, "llm")}
    out, counts = apply_classifications(df, results)
    assert out["primary_reason"].tolist() == ["FIT", "UNCLEAR"]
    assert out["classification_source"].tolist() == ["llm", "llm_low_confidence"]
    assert counts == {"applied": 1, "low_confidence": 1, "failed": 0, "still_pending": 0}


EV = {"product": "Floral Midi Dress", "segment": {"size": "L"}, "orders": 100, "returns": 40, "return_rate_pct": 40.0,
      "overall_return_rate_pct": 12.4, "lift_vs_overall": 3.2,
      "top_reasons": [{"reason": "FIT/TOO_TIGHT", "count": 28, "share_of_returns_pct": 70.0}], "body_areas": []}


def test_evaluator_catches_invented_numbers():
    assert check_numbers("40 of 100 orders (40.0%) vs 12.4% overall", EV) == []
    assert check_numbers("Returns rose 55% last month", EV) == ["Number 55 is not in the evidence"]
    bad = Recommendation(headline="Check dress", explanation="40.0% returned", suggested_action="Check sizing")
    assert any("Product name" in i for i in deterministic_checks(bad, EV))


def test_loop_retries_then_passes():
    class Seq:
        def __init__(self): self.n = 0
        def invoke(self, payload):
            self.n += 1
            txt = "Returns up 99% suggests a problem" if self.n == 1 else "40 of 100 orders were returned"
            return {"raw": None, "parsing_error": None, "parsed": Recommendation(
                headline="Floral Midi Dress fit", explanation=txt + " for Floral Midi Dress", suggested_action="Check shoulder measurements")}
    ins = {"insight_id": "x", "product_name": "Floral Midi Dress", "segment": {"size": "L"}, "orders": 100, "returns": 40,
           "return_rate": 0.4, "baseline_rate": 0.124, "lift": 3.2, "unclassified_share": 0.0,
           "reason_detail_breakdown": {"FIT/TOO_TIGHT": 28}, "body_area_breakdown": {}}
    out = generate_validated_recommendation(ins, MOCK, MOCK, CostTracker(), use_judge=False, rec_chain=Seq())
    assert out["status"] == "passed_checks" and out["attempts"] == 2


def test_loop_gives_up_to_manual_review():
    class Bad:
        def invoke(self, payload):
            return {"raw": None, "parsing_error": None, "parsed": Recommendation(
                headline="x", explanation="Returns up 99%", suggested_action="y")}
    ins = {"insight_id": "x", "product_name": "P", "segment": {}, "orders": 10, "returns": 5, "return_rate": 0.5,
           "baseline_rate": 0.1, "lift": 5.0, "unclassified_share": 0.0, "reason_detail_breakdown": {}, "body_area_breakdown": {}}
    out = generate_validated_recommendation(ins, MOCK, MOCK, CostTracker(), use_judge=False, rec_chain=Bad())
    assert out["status"] == "needs_manual_review" and out["attempts"] == aic.MAX_REC_ATTEMPTS


def test_end_to_end_mock(tmp_path):
    from ai.run import run
    returns, recs, report = run(MOCK, MOCK, out_dir=tmp_path, with_eval=True)
    assert report["applied"]["still_pending"] == 0
    assert not returns["needs_llm"].any()
    assert recs and all(r["status"] == "passed_checks" for r in recs)
    assert (tmp_path / "ai_insights.json").exists()


def test_openrouter_chain_builds(monkeypatch):
    from ai.llm import get_chat_model
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    m = get_chat_model(ModelSpec.parse("openrouter:anthropic/claude-haiku-4.5"))
    assert "openrouter.ai" in str(m.openai_api_base) and m.model_name == "anthropic/claude-haiku-4.5"
    from ai.classifier import build_classifier_chain
    assert build_classifier_chain(ModelSpec.parse("openrouter:openai/gpt-4o-mini")) is not None
    monkeypatch.delenv("OPENROUTER_API_KEY")
    import pytest
    with pytest.raises(RuntimeError):
        get_chat_model(ModelSpec.parse("openrouter:openai/gpt-4o"))


def test_check_credentials(monkeypatch):
    import pytest
    from ai.llm import AuthError, check_credentials
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(AuthError, match="ANTHROPIC_API_KEY"):
        check_credentials(ModelSpec.parse("anthropic:claude-haiku-4-5-20251001"))
    check_credentials(ModelSpec.parse("openrouter:openai/gpt-4o"), MOCK)   # fine: key present / mock needs none


def test_auth_error_aborts_instead_of_marking_rows_failed():
    import pytest
    from ai.llm import AuthError

    class NoKey:
        def invoke(self, payload):
            raise TypeError("Could not resolve authentication method. Expected one of api_key...")
    with pytest.raises(AuthError):
        classify_comments(["waist loose hai"], ModelSpec.parse("anthropic:x"), MOCK, CostTracker(), fast_chain=NoKey())


def test_provider_defaults(monkeypatch):
    from ai.llm import specs_from_env
    for k in ("LLM_FAST", "LLM_STRONG"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    f, s, _ = specs_from_env()
    assert f.provider == "openrouter" and s.provider == "openrouter"


def test_openrouter_is_the_default(monkeypatch):
    from ai.llm import specs_from_env
    for k in ("LLM_PROVIDER", "LLM_FAST", "LLM_STRONG", "LLM_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    f, s, fb = specs_from_env()
    assert (f.provider, s.provider, fb) == ("openrouter", "openrouter", None) and f != s

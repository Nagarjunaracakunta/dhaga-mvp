"""LangChain client (ChatOpenAI -> OpenRouter) against a mocked HTTP layer: no network, no credit used."""
import json

import httpx
import pytest

from backend.modules.cx.schemas import TicketClassification
from backend.shared.llm import LangChainLLM, LLMOutputError, LLMUnavailable, openrouter_model


def llm_returning(status, payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json=payload)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LangChainLLM("sk-or-test", "https://openrouter.test/api/v1", 5, http_client=client)


def call(llm, **kw):
    return llm.parse(model="claude-haiku-4-5", system="Classify {braces are safe}", user="Order {DHC1} kahan hai?",
                     output_format=TicketClassification, max_tokens=100, **kw)


def completion(content, finish="stop"):
    return {"id": "gen-1", "object": "chat.completion", "created": 0, "model": "anthropic/claude-haiku-4.5",
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "cost": 0.00027}}


GOOD = json.dumps({"intent": "WISMO", "confidence": 0.9, "order_number": None, "language": "hinglish"})


def test_model_names_map_to_openrouter_ids():
    assert openrouter_model("claude-haiku-4-5") == "anthropic/claude-haiku-4.5"
    assert openrouter_model("claude-opus-5-5") == "anthropic/claude-opus-5.5"
    assert openrouter_model("anthropic/claude-sonnet-5.5") == "anthropic/claude-sonnet-5.5"


def test_chain_parses_structured_output_and_sends_schema():
    seen = []
    r = call(llm_returning(200, completion(GOOD), seen), temperature=0, effort="low")
    assert r.parsed.intent == "WISMO" and r.cost_usd == 0.00027 and r.input_tokens == 120 and r.output_tokens == 30
    body = seen[0]
    assert body["model"] == "anthropic/claude-haiku-4.5" and body["temperature"] == 0
    assert body["reasoning"] == {"effort": "low"} and body["usage"] == {"include": True}
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"] is True
    # prompt template must not treat braces in prompts or customer text as variables
    assert body["messages"][0]["content"] == "Classify {braces are safe}"
    assert body["messages"][1]["content"] == "Order {DHC1} kahan hai?"


def test_invalid_output_and_truncation_are_output_errors():
    with pytest.raises(LLMOutputError):
        call(llm_returning(200, completion('{"intent": "NOPE", "confidence": 1, "order_number": null, "language": "english"}')))
    with pytest.raises(LLMOutputError):
        call(llm_returning(200, completion('{"intent": "WIS', finish="length")))


def test_no_credit_and_bad_requests_mean_unavailable():
    with pytest.raises(LLMUnavailable, match="credit"):
        call(llm_returning(402, {"error": {"message": "Insufficient credits", "code": 402}}))
    with pytest.raises(LLMUnavailable):
        call(llm_returning(400, {"error": {"message": "bad request", "code": 400}}))

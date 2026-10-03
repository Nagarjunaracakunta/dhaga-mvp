"""OpenRouter client against a mocked HTTP layer: no network, no credit used."""
import json

import httpx
import pytest

from backend.modules.cx.schemas import TicketClassification
from backend.shared.llm import LLMOutputError, LLMUnavailable, OpenRouterLLM, openrouter_model


def client_returning(status, payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json=payload)
    llm = OpenRouterLLM("sk-or-test", "https://openrouter.test/api/v1", 5)
    llm.client = httpx.Client(base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler))
    return llm


def call(llm, **kw):
    return llm.parse(model="claude-haiku-4-5", system="s", user="u", output_format=TicketClassification,
                     max_tokens=100, **kw)


def ok_payload(content, finish="stop"):
    return {"model": "anthropic/claude-haiku-4.5",
            "choices": [{"finish_reason": finish, "message": {"content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0.00027}}


def test_model_names_map_to_openrouter_ids():
    assert openrouter_model("claude-haiku-4-5") == "anthropic/claude-haiku-4.5"
    assert openrouter_model("claude-opus-5-5") == "anthropic/claude-opus-5.5"
    assert openrouter_model("anthropic/claude-sonnet-5.5") == "anthropic/claude-sonnet-5.5"


def test_parses_structured_output_and_sends_schema():
    seen = []
    content = json.dumps({"intent": "WISMO", "confidence": 0.9, "order_number": None, "language": "hinglish"})
    r = call(client_returning(200, ok_payload(content), seen), temperature=0, effort="low")
    assert r.parsed.intent == "WISMO" and r.cost_usd == 0.00027 and r.input_tokens == 120
    body = seen[0]
    assert body["model"] == "anthropic/claude-haiku-4.5" and body["temperature"] == 0
    assert body["reasoning"] == {"effort": "low"}
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False


def test_bad_json_and_truncation_are_output_errors():
    with pytest.raises(LLMOutputError):
        call(client_returning(200, ok_payload('{"intent": "NOPE"}')))
    with pytest.raises(LLMOutputError):
        call(client_returning(200, ok_payload("{", finish="length")))


def test_no_credit_and_server_errors_mean_unavailable():
    with pytest.raises(LLMUnavailable, match="credit"):
        call(client_returning(402, {"error": {"message": "Insufficient credits"}}))
    with pytest.raises(LLMUnavailable):
        call(client_returning(500, {"error": {"message": "boom"}}))

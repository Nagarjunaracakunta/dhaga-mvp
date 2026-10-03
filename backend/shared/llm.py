"""Claude client used by every module. Returns validated Pydantic objects plus cost and timing.

Two failure types, handled differently by callers:
- LLMUnavailable: no key, network, rate limit, server error -> callers switch to fallback mode
- LLMOutputError: the model answered but we can't use it (refusal, cut off, invalid JSON) -> hand to a human
"""
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Generic, Optional, Protocol, TypeVar

import anthropic
import httpx
import pydantic
from anthropic.lib._parse._transform import transform_schema  # makes a Pydantic schema strict-mode compatible
from pydantic import TypeAdapter

from .settings import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=pydantic.BaseModel)

# Server-side fallback: if the strong model declines, the API retries on a suitable model in the same call
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(Exception):
    pass


class LLMOutputError(Exception):
    pass


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class LLM(Protocol):
    """What the modules depend on. Tests pass a fake with the same method."""

    def parse(self, *, model: str, system: str, user: str, output_format: type[T], max_tokens: int,
              temperature: Optional[float] = None, effort: Optional[str] = None,
              allow_fallback_model: bool = False) -> LLMResult[T]: ...


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = get_settings().price_per_mtok.get(model, (0.0, 0.0))
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)


class ClaudeLLM:
    def __init__(self, api_key: str, timeout_s: float):
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=2)

    def parse(self, *, model, system, user, output_format, max_tokens,
              temperature=None, effort=None, allow_fallback_model=False):
        kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                      messages=[{"role": "user", "content": user}], output_format=output_format)
        if effort:
            kwargs["output_config"] = {"effort": effort}
        if temperature is not None:
            # Not a typed SDK argument any more; only sent to models that accept it (Haiku 4.5)
            kwargs["extra_body"] = {"temperature": temperature}

        start = time.perf_counter()
        try:
            if allow_fallback_model:
                resp = self.client.beta.messages.parse(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.parse(**kwargs)
        except pydantic.ValidationError as e:
            raise LLMOutputError(f"{model} returned output that failed the schema: {e.error_count()} errors") from e
        except anthropic.AuthenticationError as e:
            raise LLMUnavailable("Claude API key was rejected") from e
        except anthropic.RateLimitError as e:
            raise LLMUnavailable("Claude API rate limit reached") from e
        except anthropic.BadRequestError as e:
            log.error("Claude rejected the request for %s: %s", model, e.message)
            raise LLMUnavailable(f"Claude rejected the request: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMUnavailable(f"Claude API error {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise LLMUnavailable("Could not reach the Claude API") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.stop_reason == "refusal":
            raise LLMOutputError(f"{model} declined to answer")
        if resp.stop_reason == "max_tokens":
            raise LLMOutputError(f"{model} ran out of tokens before finishing")
        if resp.parsed_output is None:
            raise LLMOutputError(f"{model} returned no structured output")

        served_by = getattr(resp, "model", None) or model
        usage = resp.usage
        return LLMResult(parsed=resp.parsed_output, model=served_by,
                         input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                         cost_usd=cost_usd(served_by, usage.input_tokens, usage.output_tokens),
                         latency_ms=latency_ms)


def openrouter_model(model: str) -> str:
    """claude-haiku-4-5 -> anthropic/claude-haiku-4.5, claude-opus-5-5 -> anthropic/claude-opus-5.5"""
    if "/" in model:
        return model
    family, *version = model.split("-")[1:]  # drop the "claude" prefix
    return f"anthropic/claude-{family}-{'.'.join(version)}"


class OpenRouterLLM:
    """Same Claude models through OpenRouter's chat-completions API, with JSON-schema structured output."""

    def __init__(self, api_key: str, base_url: str, timeout_s: float):
        self.client = httpx.Client(base_url=base_url, timeout=timeout_s,
                                   headers={"Authorization": f"Bearer {api_key}", "X-Title": "Dhaga Workbench"})

    def parse(self, *, model, system, user, output_format, max_tokens,
              temperature=None, effort=None, allow_fallback_model=False):
        schema = transform_schema(TypeAdapter(output_format).json_schema())
        body = {
            "model": openrouter_model(model),
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": output_format.__name__, "strict": True, "schema": schema}},
            "usage": {"include": True},
        }
        if temperature is not None:
            body["temperature"] = temperature
        if effort:
            body["reasoning"] = {"effort": effort}

        start = time.perf_counter()
        try:
            resp = self.client.post("/chat/completions", json=body)
        except httpx.HTTPError as e:
            raise LLMUnavailable("Could not reach OpenRouter") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200 or "error" in data:
            message = (data.get("error") or {}).get("message", resp.text[:200])
            log.error("OpenRouter %s for %s: %s", resp.status_code, model, message)
            if resp.status_code == 402:
                raise LLMUnavailable("OpenRouter credit used up")
            raise LLMUnavailable(f"OpenRouter error {resp.status_code}: {message}")

        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMOutputError(f"{model} ran out of tokens before finishing")
        if choice.get("finish_reason") in ("content_filter", "refusal") or choice["message"].get("refusal"):
            raise LLMOutputError(f"{model} declined to answer")
        try:
            parsed = output_format.model_validate_json(choice["message"].get("content") or "")
        except pydantic.ValidationError as e:
            raise LLMOutputError(f"{model} returned output that failed the schema: {e.error_count()} errors") from e

        usage = data.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cost = usage.get("cost")
        return LLMResult(parsed=parsed, model=data.get("model") or openrouter_model(model),
                         input_tokens=tokens_in, output_tokens=tokens_out,
                         cost_usd=round(cost, 6) if isinstance(cost, (int, float)) else cost_usd(model, tokens_in, tokens_out),
                         latency_ms=latency_ms)


class UnconfiguredLLM:
    """Used when no model key is set, so the app still runs in fallback mode."""

    def parse(self, **_):
        raise LLMUnavailable("No ANTHROPIC_API_KEY or OPENROUTER_API_KEY set")


@lru_cache
def get_llm() -> LLM:
    s = get_settings()
    if s.llm_provider == "anthropic":
        return ClaudeLLM(s.anthropic_api_key, s.llm_timeout_s)
    if s.llm_provider == "openrouter":
        return OpenRouterLLM(s.openrouter_api_key, s.openrouter_base_url, s.llm_timeout_s)
    return UnconfiguredLLM()

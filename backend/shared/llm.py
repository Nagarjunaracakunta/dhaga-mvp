"""Model clients used by every module. Return validated Pydantic objects plus cost and timing.

- LangChainLLM (default): LangChain chain against OpenRouter. Used when OPENROUTER_API_KEY is set.
- ClaudeLLM: Anthropic SDK directly, used only if ANTHROPIC_API_KEY is set. Kept outside LangChain because
  LangChain's Claude structured output relies on forced tool use, which Opus 5.5 / Sonnet 5.5 reject.

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
import openai
import pydantic
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

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


class LangChainLLM:
    """LangChain chain per call: ChatPromptTemplate | ChatOpenAI.with_structured_output(schema).

    ChatOpenAI points at OpenRouter's OpenAI-compatible API, so the same Claude models run through LangChain.
    LangChain handles the prompt template, the provider call, retries, and parsing the JSON-schema
    output into our Pydantic model.
    """

    PROMPT = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])

    def __init__(self, api_key: str, base_url: str, timeout_s: float, http_client: Optional[httpx.Client] = None):
        self.api_key, self.base_url, self.timeout_s, self.http_client = api_key, base_url, timeout_s, http_client

    def _chat_model(self, model, max_tokens, temperature, effort) -> ChatOpenAI:
        extra_body = {"usage": {"include": True}}  # ask OpenRouter to return the cost of each call
        if effort:
            extra_body["reasoning"] = {"effort": effort}
        kwargs = dict(model=openrouter_model(model), api_key=self.api_key, base_url=self.base_url,
                      timeout=self.timeout_s, max_retries=2, max_tokens=max_tokens, extra_body=extra_body,
                      default_headers={"X-Title": "Dhaga Workbench"})
        if temperature is not None:
            kwargs["temperature"] = temperature
        if self.http_client is not None:
            kwargs["http_client"] = self.http_client
        return ChatOpenAI(**kwargs)

    def parse(self, *, model, system, user, output_format, max_tokens,
              temperature=None, effort=None, allow_fallback_model=False):
        structured = self._chat_model(model, max_tokens, temperature, effort).with_structured_output(
            output_format, method="json_schema", strict=True, include_raw=True)
        chain = self.PROMPT | structured

        start = time.perf_counter()
        try:
            out = chain.invoke({"system": system, "user": user})
        except openai.LengthFinishReasonError as e:
            raise LLMOutputError(f"{model} ran out of tokens before finishing") from e
        except openai.ContentFilterFinishReasonError as e:
            raise LLMOutputError(f"{model} declined to answer") from e
        except pydantic.ValidationError as e:
            raise LLMOutputError(f"{model} returned output that failed the schema: {e.error_count()} errors") from e
        except openai.APIStatusError as e:
            log.error("OpenRouter %s for %s: %s", e.status_code, model, e.message)
            if e.status_code == 402:
                raise LLMUnavailable("OpenRouter credit used up") from e
            raise LLMUnavailable(f"OpenRouter error {e.status_code}: {e.message}") from e
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            raise LLMUnavailable("Could not reach OpenRouter") from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        raw, parsed = out["raw"], out["parsed"]
        if raw.additional_kwargs.get("refusal"):
            raise LLMOutputError(f"{model} declined to answer")
        if out["parsing_error"] is not None or parsed is None:
            raise LLMOutputError(f"{model} returned output that failed the schema: {out['parsing_error']}")

        usage = raw.usage_metadata or {}
        tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cost = (raw.response_metadata.get("token_usage") or {}).get("cost")
        served_by = raw.response_metadata.get("model_name") or openrouter_model(model)
        return LLMResult(parsed=parsed, model=served_by, input_tokens=tokens_in, output_tokens=tokens_out,
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
        return LangChainLLM(s.openrouter_api_key, s.openrouter_base_url, s.llm_timeout_s)
    return UnconfiguredLLM()

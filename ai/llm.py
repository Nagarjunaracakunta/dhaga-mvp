"""Model factory (LangChain). Provider-agnostic: a model is just 'provider:model'."""
import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional
    pass

# Default provider: OpenRouter (one key, several vendors' models). Other providers stay available as opt-in.
DEFAULT_PROVIDER = "openrouter"
DEFAULT_FAST = "openrouter:anthropic/claude-haiku-4.5"
DEFAULT_STRONG = "openrouter:openai/gpt-4o"


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @classmethod
    def parse(cls, s: str) -> "ModelSpec":
        provider, _, model = s.partition(":")
        return cls(provider.strip().lower(), (model or provider).strip())

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


# Each provider has its OWN key. A key for one provider does not work for another.
REQUIRED_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
PROVIDER_DEFAULTS = {
    "anthropic": ("anthropic:claude-haiku-4-5-20251001", "anthropic:claude-sonnet-5-5"),
    "openai": ("openai:gpt-4o-mini", "openai:gpt-4o"),
    "openrouter": (DEFAULT_FAST, DEFAULT_STRONG),
}


class AuthError(RuntimeError):
    """Missing/invalid API key: retrying cannot help, so the run stops immediately."""


def check_credentials(*specs):
    """Fail fast (before any spend or retries) if a needed API key is not set."""
    missing = sorted({REQUIRED_KEYS[s.provider] for s in specs
                      if s.provider in REQUIRED_KEYS and not os.getenv(REQUIRED_KEYS[s.provider])})
    if missing:
        used = ", ".join(sorted({s.label for s in specs}))
        raise AuthError(f"Missing {', '.join(missing)} for models [{used}]. Put the key in .env, and make sure LLM_FAST / "
                        f"LLM_STRONG (or LLM_PROVIDER, or --provider) point at the provider you have a key for.")


def _is_auth_error(e: Exception) -> bool:
    return (type(e).__name__ in ("AuthenticationError", "PermissionDeniedError")
            or "Could not resolve authentication" in str(e) or "401" in str(e)[:300])


def specs_from_env():
    d_fast, d_strong = PROVIDER_DEFAULTS.get(os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower(), (DEFAULT_FAST, DEFAULT_STRONG))
    fast = ModelSpec.parse(os.getenv("LLM_FAST", d_fast))
    strong = ModelSpec.parse(os.getenv("LLM_STRONG", d_strong))
    fb = os.getenv("LLM_FALLBACK")
    return fast, strong, (ModelSpec.parse(fb) if fb else None)


def get_chat_model(spec: ModelSpec, temperature: float = 0.0, max_tokens: int = 4096):
    if spec.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=spec.model, temperature=temperature, max_tokens=max_tokens, timeout=90)
    if spec.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=spec.model, temperature=temperature, max_tokens=max_tokens, timeout=90)
    if spec.provider == "openrouter":        # OpenAI-compatible gateway: one key, many vendors' models
        from langchain_openai import ChatOpenAI
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
        return ChatOpenAI(model=spec.model, temperature=temperature, max_tokens=max_tokens, timeout=90,
                          base_url="https://openrouter.ai/api/v1", api_key=key,
                          default_headers={"X-Title": "dhaga-mvp"})
    raise ValueError(f"Unsupported provider '{spec.provider}'. Add a branch in ai/llm.py.")


def structured_chain(prompt, schema, spec: ModelSpec, fallback: Optional[ModelSpec] = None, temperature: float = 0.0):
    """prompt | model.with_structured_output(schema) -> dict(raw, parsed, parsing_error).
    Retries transient errors; optionally falls back to a second provider/model."""
    def build(s):
        llm = get_chat_model(s, temperature=temperature)
        # Via OpenRouter, tool/function calling is the most widely supported structured-output route across vendors.
        kw = {"method": "function_calling"} if s.provider == "openrouter" else {}
        return (prompt | llm.with_structured_output(schema, include_raw=True, **kw)).with_retry(stop_after_attempt=3)
    chain = build(spec)
    if fallback and fallback != spec:
        chain = chain.with_fallbacks([build(fallback)])
    return chain


def invoke_tracked(chain, payload: dict, spec: ModelSpec, tracker):
    """Run a chain, record token usage, return the parsed object or None if it failed to parse."""
    try:
        out = chain.invoke(payload)
    except Exception as e:
        if _is_auth_error(e):
            raise AuthError(f"Authentication failed for {spec.label}: check the API key for that provider ({e})") from e
        raise
    usage = getattr(out.get("raw"), "usage_metadata", None) or {}
    tracker.record(spec, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    if out.get("parsing_error") or out.get("parsed") is None:
        return None
    return out["parsed"]

import pytest

from backend.modules.cx.copilot import Deps
from backend.modules.cx.knowledge import KnowledgeBase
from backend.modules.cx.repository import DemoRepository
from backend.shared.llm import LLMResult, UnconfiguredLLM
from backend.shared.settings import Settings
from backend.modules.cx.schemas import DraftCheck, DraftReply, TicketClassification


class FakeLLM:
    """Stands in for Claude. Give it one handler per output schema; it records every call."""

    def __init__(self, classify=None, draft=None, check=None):
        self.handlers = {TicketClassification: classify, DraftReply: draft, DraftCheck: check}
        self.calls = []

    def parse(self, *, model, system, user, output_format, max_tokens, temperature=None, effort=None,
              allow_fallback_model=False):
        self.calls.append({"model": model, "schema": output_format.__name__, "user": user,
                           "temperature": temperature, "effort": effort})
        handler = self.handlers[output_format]
        parsed = handler(user) if callable(handler) else handler
        if isinstance(parsed, Exception):
            raise parsed
        return LLMResult(parsed=parsed, model=model, input_tokens=100, output_tokens=50, cost_usd=0.001, latency_ms=5)


@pytest.fixture
def settings():
    return Settings(_env_file=None, supabase_url="", supabase_service_key="", anthropic_api_key="")


@pytest.fixture
def repo():
    return DemoRepository()


def make_deps(repo, settings, llm=None):
    return Deps(repo=repo, llm=llm or UnconfiguredLLM(), kb=KnowledgeBase(repo), settings=settings)

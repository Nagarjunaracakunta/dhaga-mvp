"""Model call 1: what does the customer want? (Haiku 4.5, temperature 0)"""
from pathlib import Path

from backend.shared.llm import LLM, LLMResult
from backend.shared.settings import Settings

from .schemas import TicketClassification

PROMPT_VERSION = "classify_v1"
SYSTEM = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text()


def classify(llm: LLM, message: str, settings: Settings) -> LLMResult[TicketClassification]:
    result = llm.parse(model=settings.model_fast, system=SYSTEM, user=f"<ticket>\n{message}\n</ticket>",
                       output_format=TicketClassification, max_tokens=512, temperature=0)
    c = result.parsed
    c.confidence = min(max(c.confidence, 0.0), 1.0)
    c.order_number = c.order_number.strip().upper() if c.order_number else None
    return result

"""Model call 2: write the reply (Opus 5.5, effort low). Facts and policy come in; the model only words them."""
import json
from pathlib import Path
from typing import Optional

from backend.shared.llm import LLM, LLMResult
from backend.shared.settings import Settings

from .repository import Policy
from .schemas import DraftReply, OrderFacts, TicketClassification

PROMPT_VERSION = "draft_v1"
SYSTEM = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text()


def build_user_prompt(*, message: str, first_name: str, classification: TicketClassification,
                      facts: OrderFacts, policy: Optional[Policy], priority_note: Optional[str],
                      previous_issues: list[str]) -> str:
    parts = [
        f"<customer_first_name>{first_name}</customer_first_name>",
        f"<customer_message>\n{message}\n</customer_message>",
        f"<intent>{classification.intent}</intent>",
        f"<customer_language>{classification.language}</customer_language>",
        f"<order_facts>\n{json.dumps(facts.model_dump(mode='json'), indent=2)}\n</order_facts>",
        f"<policy name=\"{policy.name}\">\n{policy.text}\n</policy>" if policy else "<policy>No policy document available. Do not state any policy.</policy>",
    ]
    if priority_note:
        parts.append(f"<priority_note>{priority_note}</priority_note>")
    if previous_issues:
        issues = "\n".join(f"- {i}" for i in previous_issues)
        parts.append(f"<previous_draft_issues>\nA reviewer rejected your last draft. Fix these:\n{issues}\n</previous_draft_issues>")
    return "\n\n".join(parts)


def draft(llm: LLM, settings: Settings, **prompt_inputs) -> LLMResult[DraftReply]:
    return llm.parse(model=settings.model_strong, system=SYSTEM, user=build_user_prompt(**prompt_inputs),
                     output_format=DraftReply, max_tokens=8000, effort=settings.draft_effort,
                     allow_fallback_model=True)

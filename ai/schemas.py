"""Structured outputs at every model boundary. Business rules (valid combos, ranges) are enforced in code."""
from pydantic import BaseModel, Field
from .taxonomy import Primary, Sub, BodyArea


class ItemClassification(BaseModel):
    id: int = Field(description="The id of the input comment this answer is for")
    primary_reason: Primary
    sub_reason: Sub
    body_area: BodyArea = Field(description="Body area for fit complaints, otherwise NONE")
    confidence: float = Field(description="0.0 to 1.0: how sure you are")


class BatchOutput(BaseModel):
    items: list[ItemClassification] = Field(description="Exactly one entry per input comment id")


class Recommendation(BaseModel):
    headline: str = Field(description="One-line title naming the product and the issue")
    explanation: str = Field(description="Short evidence-based explanation using only the provided numbers")
    suggested_action: str = Field(description="One concrete investigation step (not a final decision)")


class Verdict(BaseModel):
    passed: bool = Field(description="True only if every claim is supported by the evidence")
    issues: list[str] = Field(description="Unsupported or wrong claims; empty if passed")

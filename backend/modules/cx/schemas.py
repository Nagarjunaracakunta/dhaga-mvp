"""Every shape the CX module passes around: database records, model outputs, API responses."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Intent = Literal["WISMO", "DELIVERED_NOT_RECEIVED", "CANCEL_ORDER", "RETURN_REFUND", "COD_PAYMENT", "OTHER"]
TicketStatus = Literal["OPEN", "DRAFTED", "RESOLVED", "ESCALATED"]
ResultStatus = Literal["DRAFTED", "NEEDS_HUMAN", "NEEDS_INFO"]
HumanAction = Literal["APPROVED", "EDITED", "REJECTED", "ESCALATED"]


# ---------- Records read from the database ----------
class OrderItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    size: Optional[str] = None
    colour: Optional[str] = None
    quantity: int = 1
    unit_price: Optional[float] = None


class OrderRecord(BaseModel):
    order_id: str
    order_number: str
    customer_id: str
    order_date: Optional[datetime] = None
    payment_mode: Optional[str] = None
    order_status: str
    courier: Optional[str] = None
    tracking_number: Optional[str] = None
    expected_delivery: Optional[date] = None
    delivered_at: Optional[datetime] = None
    total_amount: Optional[float] = None
    items: list[OrderItem] = []


class TicketRecord(BaseModel):
    ticket_id: str
    ticket_number: str
    customer_id: str
    customer_name: str
    city: Optional[str] = None
    channel: Optional[str] = None
    message: str
    status: str = "OPEN"
    created_at: Optional[datetime] = None
    order_id: Optional[str] = None


# ---------- Model outputs (validated against these schemas) ----------
class TicketClassification(BaseModel):
    intent: Intent
    confidence: float = Field(description="0 to 1. How sure you are about the intent.")
    order_number: Optional[str] = Field(description="Order number exactly as written by the customer, e.g. DHC100560, or null")
    language: Literal["english", "hinglish", "hindi", "other"]


class DraftReply(BaseModel):
    reply: str
    facts_used: list[str] = Field(description="Names of the facts the reply relies on, e.g. ['status', 'expected_delivery']")


class DraftCheck(BaseModel):
    passed: bool
    issues: list[str]


# ---------- Built by code ----------
class OrderFacts(BaseModel):
    order_number: str
    status: str
    courier: Optional[str]
    tracking_number: Optional[str]
    order_date: Optional[date]
    expected_delivery: Optional[date]
    delivered_on: Optional[date]
    days_late: Optional[int] = Field(description="Days past expected delivery; null if delivered or not late")
    days_since_delivery: Optional[int]
    is_delivered: bool
    is_cancellable: bool
    within_return_window: Optional[bool]
    payment_mode: Optional[str]
    total_amount: Optional[float]
    items: list[str]


class RuleDecision(BaseModel):
    action: Literal["DRAFT", "NEEDS_HUMAN", "NEEDS_INFO"]
    reason: Optional[str] = None
    escalation_tier: Optional[str] = None
    priority_note: Optional[str] = None


# ---------- API responses ----------
class CopilotResult(BaseModel):
    ticket_id: Optional[str]
    status: ResultStatus
    classification: TicketClassification
    facts: Optional[OrderFacts]
    policy_used: Optional[str]
    draft: Optional[str]
    check: Optional[DraftCheck]
    human_reason: Optional[str]
    escalation_tier: Optional[str]
    priority_note: Optional[str]
    attempts: int
    fallback_mode: bool
    notes: list[str] = []
    interaction_id: Optional[str]
    cost_usd: float
    latency_ms: int


class TicketSummary(BaseModel):
    ticket_id: str
    ticket_number: str
    customer_name: str
    channel: Optional[str]
    message: str
    status: str
    created_at: Optional[datetime]
    last_intent: Optional[str] = None
    last_result: Optional[str] = None


class TicketDetail(BaseModel):
    ticket: TicketRecord
    order: Optional[OrderRecord]
    facts: Optional[OrderFacts]
    last_result: Optional[dict] = None


class DecisionRequest(BaseModel):
    interaction_id: str
    action: HumanAction
    final_reply: Optional[str] = None


class DecisionResponse(BaseModel):
    ticket_id: str
    ticket_status: str
    human_action: str


class AnalyzeTextRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    customer_id: Optional[str] = None
    order_number: Optional[str] = None


class CXMetrics(BaseModel):
    tickets_by_status: dict[str, int]
    analysed: int
    by_intent: dict[str, int]
    by_result: dict[str, int]
    human_actions: dict[str, int]
    acceptance_rate: Optional[float]
    fallback_runs: int
    avg_latency_ms: Optional[int]
    avg_cost_usd: Optional[float]
    total_cost_usd: float

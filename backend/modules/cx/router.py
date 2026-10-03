"""CX Copilot API. Mounted at /api/cx. Routes only parse input and call service functions."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from . import bulk, service
from .copilot import Deps
from .schemas import (AnalyzeTextRequest, BulkApproveRequest, BulkApproveResponse, BulkDraftRequest,
                      BulkDraftResponse, BulkQueue, CopilotResult, CXMetrics, DecisionRequest, DecisionResponse,
                      InboxPage, InboxSort, InboxView, TicketDetail, TicketSummary)

router = APIRouter(tags=["cx"])


@router.get("/tickets", response_model=list[TicketSummary])
def list_tickets(status: Optional[str] = Query(None, pattern="^(OPEN|DRAFTED|RESOLVED|ESCALATED)$"),
                 channel: Optional[str] = None, intent: Optional[str] = None,
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 deps: Deps = Depends(service.get_deps)):
    return service.list_tickets(deps, status, channel, intent, limit, offset)


@router.get("/inbox", response_model=InboxPage)
def inbox(view: InboxView = "all", intent: Optional[str] = None, q: Optional[str] = Query(None, max_length=100),
          sort: InboxSort = "priority", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
          deps: Deps = Depends(service.get_deps)):
    """Search, views and priority across every ticket (not just one page)."""
    return service.inbox(deps, view, intent, q, sort, limit, offset)


@router.get("/tickets/{ticket_ref}", response_model=TicketDetail)
def get_ticket(ticket_ref: str, deps: Deps = Depends(service.get_deps)):
    """ticket_ref is the ticket UUID or its number, e.g. TKT200001."""
    return service.ticket_detail(deps, ticket_ref)


@router.post("/tickets/{ticket_ref}/analyze", response_model=CopilotResult)
def analyze_ticket(ticket_ref: str, deps: Deps = Depends(service.get_deps)):
    return service.analyze_ticket(deps, ticket_ref)


@router.post("/tickets/{ticket_ref}/decision", response_model=DecisionResponse)
def decide(ticket_ref: str, body: DecisionRequest, deps: Deps = Depends(service.get_deps)):
    return service.record_decision(deps, ticket_ref, body)


@router.post("/analyze", response_model=CopilotResult)
def analyze_text(body: AnalyzeTextRequest, deps: Deps = Depends(service.get_deps)):
    """Run Copilot on pasted text (demo use). Not linked to a ticket."""
    return service.analyze_text(deps, body)


@router.get("/orders/{order_number}")
def get_order(order_number: str, deps: Deps = Depends(service.get_deps)):
    return service.order_lookup(deps, order_number)


@router.get("/metrics", response_model=CXMetrics)
def get_metrics(deps: Deps = Depends(service.get_deps)):
    return service.metrics(deps)


@router.get("/bulk/queue", response_model=BulkQueue)
def bulk_queue(deps: Deps = Depends(service.get_deps)):
    """Drafts ready for group review: passed checks, intent confidence >= the bulk threshold, not yet decided."""
    return bulk.queue(deps)


@router.post("/bulk/draft", response_model=BulkDraftResponse)
def bulk_draft(body: BulkDraftRequest, deps: Deps = Depends(service.get_deps)):
    """Run Copilot on the oldest open tickets. Costs model credit, so the batch size is capped."""
    return bulk.draft_open_tickets(deps, body.limit)


@router.post("/bulk/approve", response_model=BulkApproveResponse)
def bulk_approve(body: BulkApproveRequest, deps: Deps = Depends(service.get_deps)):
    """An agent approves the drafts they selected. Each one is checked again before it is recorded."""
    return bulk.approve(deps, body)

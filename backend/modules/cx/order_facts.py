"""Turn an order record into plain facts. All date arithmetic lives here, never in a prompt."""
from datetime import date
from typing import Optional

from .schemas import OrderFacts, OrderRecord

DELIVERED = "DELIVERED"
CANCELLED = "CANCELLED"
CANCELLABLE_STATUSES = {"CONFIRMED"}          # before dispatch
CLOSED_STATUSES = {DELIVERED, CANCELLED}


def _item_label(item) -> str:
    extras = ", ".join(x for x in [item.size, item.colour] if x)
    label = f"{item.product_name} ({extras})" if extras else item.product_name
    return f"{label} x{item.quantity}" if item.quantity and item.quantity > 1 else label


def build_facts(order: OrderRecord, today: date, return_window_days: int) -> OrderFacts:
    delivered_on: Optional[date] = order.delivered_at.date() if order.delivered_at else None
    is_delivered = order.order_status == DELIVERED

    days_late = None
    if not is_delivered and order.order_status != CANCELLED and order.expected_delivery:
        late = (today - order.expected_delivery).days
        days_late = late if late > 0 else None

    days_since = (today - delivered_on).days if (is_delivered and delivered_on) else None
    in_window = (days_since <= return_window_days) if days_since is not None else None

    return OrderFacts(
        order_number=order.order_number,
        status=order.order_status,
        courier=order.courier,
        tracking_number=order.tracking_number,
        order_date=order.order_date.date() if order.order_date else None,
        expected_delivery=order.expected_delivery,
        delivered_on=delivered_on,
        days_late=days_late,
        days_since_delivery=days_since,
        is_delivered=is_delivered,
        is_cancellable=order.order_status in CANCELLABLE_STATUSES,
        within_return_window=in_window,
        payment_mode=order.payment_mode,
        total_amount=order.total_amount,
        items=[_item_label(i) for i in order.items],
    )

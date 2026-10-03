"""Policy documents, loaded once and picked by intent. No vector search: each policy is short enough to send whole."""
from typing import Optional

from .repository import CXRepository, Policy

INTENT_POLICY = {
    "WISMO": "delivery",
    "DELIVERED_NOT_RECEIVED": "escalation",
    "CANCEL_ORDER": "cancellation",
    "RETURN_REFUND": "returns",
    "COD_PAYMENT": "cod",
}


class KnowledgeBase:
    def __init__(self, repo: CXRepository):
        self._repo = repo
        self._policies: Optional[dict[str, Policy]] = None

    def policies(self) -> dict[str, Policy]:
        if self._policies is None:
            self._policies = self._repo.load_policies()
        return self._policies

    def for_intent(self, intent: str) -> Optional[Policy]:
        key = INTENT_POLICY.get(intent)
        return self.policies().get(key) if key else None

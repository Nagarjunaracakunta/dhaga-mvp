"""All CX reads and writes. Nothing else in the module talks to the database.

SupabaseRepository reads the live tables. DemoRepository serves data/cx_demo/ from memory so the
module runs (and tests run) without credentials. Both have the same methods.
"""
import io
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from backend.shared.db import execute
from backend.shared.errors import AppError
from backend.shared.settings import ROOT

from .schemas import OrderItem, OrderRecord, TicketRecord

log = logging.getLogger(__name__)
WORKFLOW = "CX_COPILOT"
TICKET_STATUSES = ["OPEN", "DRAFTED", "RESOLVED", "ESCALATED"]
DEMO_DIR = ROOT / "data" / "cx_demo"
DEMO_TODAY = date(2026, 10, 3)


@dataclass
class Policy:
    key: str        # delivery | cancellation | returns | cod | escalation
    name: str
    text: str


def policy_key(*labels: str) -> Optional[str]:
    """Map a document's name/type to one of our policy keys."""
    s = " ".join(x for x in labels if x).lower()
    for key, words in [("escalation", ["escalation", "sop"]), ("cancellation", ["cancel"]),
                       ("cod", ["cod", "rto", "cash on delivery"]), ("returns", ["return", "refund"]),
                       ("delivery", ["delivery", "shipping", "wismo"])]:
        if any(w in s for w in words) and "taxonomy" not in s and "copy" not in s:
            return key
    return None


class CXRepository(Protocol):
    mode: str
    today_default: Optional[date]

    def list_tickets(self, status: Optional[str], channel: Optional[str], limit: int, offset: int) -> list[TicketRecord]: ...
    def get_ticket(self, ref: str) -> Optional[TicketRecord]: ...
    def get_order(self, order_id: str) -> Optional[OrderRecord]: ...
    def find_order(self, order_number: str) -> Optional[OrderRecord]: ...
    def latest_order(self, customer_id: str) -> Optional[OrderRecord]: ...
    def update_ticket_status(self, ticket_id: str, status: str) -> None: ...
    def insert_interaction(self, row: dict) -> str: ...
    def get_interaction(self, interaction_id: str) -> Optional[dict]: ...
    def update_interaction(self, interaction_id: str, fields: dict) -> None: ...
    def latest_interactions(self, ticket_ids: list[str]) -> dict[str, dict]: ...
    def list_interactions(self) -> list[dict]: ...
    def count_tickets_by_status(self) -> dict[str, int]: ...
    def load_policies(self) -> dict[str, Policy]: ...
    def setup_issues(self) -> list[str]: ...
    def ping(self) -> bool: ...


def load_local_policies(policy_dir: Path = DEMO_DIR / "policies") -> dict[str, Policy]:
    """Placeholder policy texts shipped in data/cx_demo/policies/."""
    out = {}
    for path in sorted(policy_dir.glob("*.md")):
        key = policy_key(path.stem)
        text = path.read_text()
        if key:
            out[key] = Policy(key, text.splitlines()[0].lstrip("# ").strip(), text)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ====================================================================== Demo
class DemoRepository:
    mode = "demo"
    today_default = DEMO_TODAY

    def __init__(self, data_dir: Path = DEMO_DIR):
        raw = json.loads((data_dir / "demo_data.json").read_text())
        self.customers = {c["customer_id"]: c for c in raw["customers"]}
        self.products = {p["product_id"]: p for p in raw["products"]}
        self.orders = {o["order_id"]: o for o in raw["orders"]}
        self.items = raw["order_items"]
        self.tickets = {t["ticket_id"]: dict(t) for t in raw["support_tickets"]}
        self.interactions: dict[str, dict] = {}
        self.policy_dir = data_dir / "policies"

    def _ticket(self, t: dict) -> TicketRecord:
        c = self.customers[t["customer_id"]]
        return TicketRecord(**t, customer_name=c["name"], city=c.get("city"))

    def _order(self, o: dict) -> OrderRecord:
        items = [OrderItem(product_id=i["product_id"], product_name=self.products[i["product_id"]]["product_name"],
                           size=i.get("size"), colour=i.get("colour"), quantity=i.get("quantity", 1),
                           unit_price=i.get("unit_price"))
                 for i in self.items if i["order_id"] == o["order_id"]]
        return OrderRecord(**o, items=items)

    def list_tickets(self, status, channel, limit, offset):
        rows = [t for t in self.tickets.values()
                if (not status or t["status"] == status) and (not channel or t["channel"] == channel)]
        rows.sort(key=lambda t: t["ticket_number"])
        return [self._ticket(t) for t in rows[offset:offset + limit]]

    def get_ticket(self, ref):
        t = self.tickets.get(ref) or next((x for x in self.tickets.values() if x["ticket_number"] == ref), None)
        return self._ticket(t) if t else None

    def get_order(self, order_id):
        o = self.orders.get(order_id)
        return self._order(o) if o else None

    def find_order(self, order_number):
        o = next((x for x in self.orders.values() if x["order_number"] == order_number), None)
        return self._order(o) if o else None

    def latest_order(self, customer_id):
        mine = [o for o in self.orders.values() if o["customer_id"] == customer_id]
        return self._order(max(mine, key=lambda o: o["order_date"])) if mine else None

    def update_ticket_status(self, ticket_id, status):
        self.tickets[ticket_id]["status"] = status

    def insert_interaction(self, row):
        iid = str(uuid.uuid4())
        self.interactions[iid] = {**row, "interaction_id": iid, "created_at": _now_iso()}
        return iid

    def get_interaction(self, interaction_id):
        return self.interactions.get(interaction_id)

    def update_interaction(self, interaction_id, fields):
        self.interactions[interaction_id].update(fields)

    def latest_interactions(self, ticket_ids):
        out = {}
        for row in sorted(self.interactions.values(), key=lambda r: r["created_at"]):
            if row.get("input_reference_id") in ticket_ids:
                out[row["input_reference_id"]] = row
        return out

    def list_interactions(self):
        return list(self.interactions.values())

    def count_tickets_by_status(self):
        counts = {s: 0 for s in TICKET_STATUSES}
        for t in self.tickets.values():
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        return counts

    def load_policies(self):
        return load_local_policies(self.policy_dir)

    def setup_issues(self):
        return []

    def ping(self):
        return True


# ====================================================================== Supabase
ORDER_SELECT = ("order_id,order_number,customer_id,order_date,payment_mode,order_status,courier,"
                "tracking_number,expected_delivery,delivered_at,total_amount,"
                "order_items(product_id,quantity,unit_price,size,colour,products(product_name))")
TICKET_SELECT = "ticket_id,ticket_number,customer_id,channel,message,status,created_at,order_id,customers(name,city)"
TICKET_NUMBER = re.compile(r"^TKT\d+$", re.I)
PAGE = 1000  # PostgREST returns at most 1000 rows per request by default
MISSING_TABLE = "PGRST205"
SETUP_SQL = "db/cx_tables.sql"

# The live support_tickets table uses OPEN / IN_PROGRESS / CLOSED. The app's statuses map onto those;
# ESCALATED has no existing equivalent, so it is written as-is.
STATUS_TO_DB = {"OPEN": "OPEN", "DRAFTED": "IN_PROGRESS", "RESOLVED": "CLOSED", "ESCALATED": "ESCALATED"}
STATUS_FROM_DB = {v: k for k, v in STATUS_TO_DB.items()}


def _is_missing_table(e: Exception) -> bool:
    return getattr(e, "code", None) == MISSING_TABLE


class SupabaseRepository:
    mode = "supabase"
    today_default = None

    def __init__(self, client, bucket: str):
        self.sb = client
        self.bucket = bucket

    def _run(self, query, what: str):
        try:
            return execute(query)
        except Exception as e:  # postgrest/httpx errors all mean "database unavailable" to the caller
            if _is_missing_table(e):
                raise AppError("DB_TABLE_MISSING", f"Could not {what}: a table is missing. "
                               f"Run {SETUP_SQL} in the Supabase SQL editor.", 503) from e
            log.exception("Supabase query failed: %s", what)
            raise AppError("DB_ERROR", f"Database error while trying to {what}", 503) from e

    def _read_interactions(self, query, what, empty):
        """ai_interactions may not exist yet; reads then return nothing instead of breaking the inbox."""
        try:
            return execute(query).data
        except Exception as e:
            if _is_missing_table(e):
                log.warning("ai_interactions table is missing; run %s", SETUP_SQL)
                return empty
            log.exception("Supabase query failed: %s", what)
            raise AppError("DB_ERROR", f"Database error while trying to {what}", 503) from e

    @staticmethod
    def _ticket(row: dict) -> TicketRecord:
        cust = row.pop("customers", None) or {}
        row["status"] = STATUS_FROM_DB.get(row.get("status"), row.get("status") or "OPEN")
        return TicketRecord(**row, customer_name=cust.get("name") or "Unknown customer", city=cust.get("city"))

    @staticmethod
    def _order(row: dict) -> OrderRecord:
        items = []
        for i in row.pop("order_items", None) or []:
            product = i.pop("products", None) or {}
            items.append(OrderItem(**i, product_name=product.get("product_name") or "Unknown product"))
        return OrderRecord(**row, items=items)

    def list_tickets(self, status, channel, limit, offset):
        q = self.sb.table("support_tickets").select(TICKET_SELECT)
        if status:
            q = q.eq("status", STATUS_TO_DB.get(status, status))
        if channel:
            q = q.eq("channel", channel)
        q = q.order("ticket_number").range(offset, offset + limit - 1)
        return [self._ticket(r) for r in self._run(q, "list tickets").data]

    def get_ticket(self, ref):
        col = "ticket_number" if TICKET_NUMBER.match(ref) else "ticket_id"
        q = self.sb.table("support_tickets").select(TICKET_SELECT).eq(col, ref).limit(1)
        rows = self._run(q, "load a ticket").data
        return self._ticket(rows[0]) if rows else None

    def _one_order(self, column, value, what):
        rows = self._run(self.sb.table("orders").select(ORDER_SELECT).eq(column, value).limit(1), what).data
        return self._order(rows[0]) if rows else None

    def get_order(self, order_id):
        return self._one_order("order_id", order_id, "load an order")

    def find_order(self, order_number):
        return self._one_order("order_number", order_number, "find an order by number")

    def latest_order(self, customer_id):
        q = (self.sb.table("orders").select(ORDER_SELECT).eq("customer_id", customer_id)
             .order("order_date", desc=True).limit(1))
        rows = self._run(q, "find the customer's latest order").data
        return self._order(rows[0]) if rows else None

    def update_ticket_status(self, ticket_id, status):
        self._run(self.sb.table("support_tickets").update({"status": STATUS_TO_DB.get(status, status)})
                  .eq("ticket_id", ticket_id),
                  "update the ticket status")

    def insert_interaction(self, row):
        data = self._run(self.sb.table("ai_interactions").insert(row), "save the AI interaction").data
        return data[0]["interaction_id"]

    def get_interaction(self, interaction_id):
        rows = self._read_interactions(
            self.sb.table("ai_interactions").select("*").eq("interaction_id", interaction_id).limit(1),
            "load the AI interaction", [])
        return rows[0] if rows else None

    def update_interaction(self, interaction_id, fields):
        self._run(self.sb.table("ai_interactions").update(fields).eq("interaction_id", interaction_id),
                  "update the AI interaction")

    def latest_interactions(self, ticket_ids):
        if not ticket_ids:
            return {}
        q = (self.sb.table("ai_interactions").select("*").eq("workflow", WORKFLOW)
             .in_("input_reference_id", ticket_ids).order("created_at"))
        out = {}
        for row in self._read_interactions(q, "load recent AI results", []):
            out[row["input_reference_id"]] = row
        return out

    def list_interactions(self):
        rows, start = [], 0
        while True:
            q = (self.sb.table("ai_interactions")
                 .select("output,confidence,evaluation_status,human_action,processing_time_ms")
                 .eq("workflow", WORKFLOW).range(start, start + PAGE - 1))
            batch = self._read_interactions(q, "load AI interactions", [])
            rows += batch
            if len(batch) < PAGE:
                return rows
            start += PAGE

    def count_tickets_by_status(self):
        counts = {}
        for s in TICKET_STATUSES:
            q = (self.sb.table("support_tickets").select("ticket_id", count="exact")
                 .eq("status", STATUS_TO_DB[s]).limit(1))
            counts[s] = self._run(q, "count tickets").count or 0
        return counts

    def load_policies(self):
        from pypdf import PdfReader
        q = self.sb.table("knowledge_documents").select("*").eq("active", True)
        out = {}
        try:
            docs = q.execute().data
        except Exception as e:
            if not _is_missing_table(e):
                log.exception("Could not list knowledge documents")
            docs = []
        for doc in docs:
            key = policy_key(doc.get("document_type"), doc.get("document_name"))
            path = (doc.get("storage_path") or "").removeprefix(f"{self.bucket}/")
            if not key or not path:
                continue
            try:
                pdf = self.sb.storage.from_(self.bucket).download(path)
                text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
            except Exception:
                log.exception("Could not load policy %s from storage path %s", doc.get("document_name"), path)
                continue
            version = f" {doc['version']}" if doc.get("version") else ""
            out[key] = Policy(key, f"{doc['document_name']}{version}", text.strip())
        # Any policy not found in Supabase falls back to the local placeholder text
        return {**load_local_policies(), **out}

    def setup_issues(self) -> list[str]:
        issues = []
        for table in ["ai_interactions", "knowledge_documents"]:
            try:
                self.sb.table(table).select("*").limit(1).execute()
            except Exception as e:
                if _is_missing_table(e):
                    issues.append(f"Table {table} is missing: run {SETUP_SQL} in the Supabase SQL editor")
        return issues

    def ping(self):
        try:
            self.sb.table("support_tickets").select("ticket_id").limit(1).execute()
            return True
        except Exception:
            return False

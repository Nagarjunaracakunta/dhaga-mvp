"""Load returns data from Supabase in the same shape as the demo CSVs, so the rest of the pipeline is unchanged.

Supabase keeps one row per order item; each order has one item, so an order item stands in for an order.
Returns carry no size, colour or product of their own: they come from the order item they point at.
"""
import pandas as pd

from backend.shared.db import execute, get_supabase

PAGE = 1000  # PostgREST returns at most 1000 rows per request


def _all(table: str, select: str) -> list[dict]:
    sb, rows, start = get_supabase(), [], 0
    while True:
        batch = execute(sb.table(table).select(select).range(start, start + PAGE - 1)).data
        rows += batch
        if len(batch) < PAGE:
            return rows
        start += PAGE


def _day(ts) -> str:
    return (ts or "")[:10]


def load_products() -> pd.DataFrame:
    rows = _all("products", "product_id,sku,product_name,category")
    return pd.DataFrame(rows, dtype=str)[["product_id", "product_name", "category", "sku"]]


def load_orders() -> pd.DataFrame:
    rows = _all("order_items", "order_item_id,product_id,size,colour,orders(order_id,customer_id,order_date,order_status)")
    out = [{"order_id": r["orders"]["order_id"], "customer_id": r["orders"]["customer_id"], "product_id": r["product_id"],
            "size": r["size"] or "", "colour": r["colour"] or "", "order_date": _day(r["orders"]["order_date"]),
            "order_item_id": r["order_item_id"], "order_status": r["orders"]["order_status"]} for r in rows]
    return pd.DataFrame(out, dtype=str)


def load_returns() -> pd.DataFrame:
    rows = _all("returns", "return_id,order_item_id,customer_id,original_reason,customer_comment,created_at,"
                           "ai_category,ai_subcategory,ai_confidence,final_category,"
                           "order_items(order_id,product_id,size,colour,products(product_name,category))")
    out = []
    for r in rows:
        item = r.get("order_items") or {}
        product = item.get("products") or {}
        out.append({
            "return_id": r["return_id"], "order_id": item.get("order_id") or "", "customer_id": r["customer_id"],
            "product_id": item.get("product_id") or "", "product_name": product.get("product_name") or "",
            "category": product.get("category") or "", "size": item.get("size") or "", "colour": item.get("colour") or "",
            "return_reason": r["original_reason"] or "", "return_comment": r["customer_comment"] or "",
            "return_date": _day(r["created_at"]), "order_item_id": r["order_item_id"],
            "ai_category": r["ai_category"], "ai_subcategory": r["ai_subcategory"],
            "ai_confidence": r["ai_confidence"], "final_category": r["final_category"],
        })
    df = pd.DataFrame(out)
    text_cols = [c for c in df.columns if c not in ("ai_category", "ai_subcategory", "ai_confidence", "final_category")]
    df[text_cols] = df[text_cols].fillna("").astype(str)
    return df

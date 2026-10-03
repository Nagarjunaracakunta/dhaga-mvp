"""Structural validation. Returns (clean_df, rejected_df). Never silently drops rows."""
import pandas as pd
from . import config

REJECT_COLUMNS = ["source", "record_id", "reason"]


def _blank(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip() == ""


def _bad_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format=config.DATE_FORMAT, errors="coerce").isna()


def _apply_checks(df: pd.DataFrame, id_col: str, source: str, checks):
    """checks: ordered list of (reason, boolean Series). First failing check wins per row."""
    keep = pd.Series(True, index=df.index)
    rejected = []
    for reason, bad in checks:
        bad = bad & keep
        rejected += [
            {"source": source, "record_id": df.at[i, id_col], "reason": reason}
            for i in df.index[bad]
        ]
        keep &= ~bad
    return df[keep].copy(), pd.DataFrame(rejected, columns=REJECT_COLUMNS)


def validate_orders(orders: pd.DataFrame, products: pd.DataFrame):
    checks = [(f"missing_{c}", _blank(orders[c])) for c in config.REQUIRED_ORDER_FIELDS]
    checks += [
        ("duplicate_order_id", orders.duplicated("order_id", keep="first")),
        ("unknown_product_id", ~orders["product_id"].isin(products["product_id"])),
        ("invalid_order_date", _bad_date(orders["order_date"])),
    ]
    clean, rejected = _apply_checks(orders, "order_id", "orders", checks)
    clean["order_date"] = pd.to_datetime(clean["order_date"], format=config.DATE_FORMAT)
    return clean, rejected


def validate_returns(returns: pd.DataFrame, orders: pd.DataFrame, products: pd.DataFrame):
    order_product = orders.set_index("order_id")["product_id"]
    checks = [(f"missing_{c}", _blank(returns[c])) for c in config.REQUIRED_RETURN_FIELDS]
    checks += [
        ("duplicate_return_id", returns.duplicated("return_id", keep="first")),
        ("invalid_return_date", _bad_date(returns["return_date"])),
        ("unknown_product_id", ~returns["product_id"].isin(products["product_id"])),
        ("order_not_found", ~returns["order_id"].isin(order_product.index)),
        ("product_mismatch_with_order", returns["product_id"] != returns["order_id"].map(order_product)),
    ]
    clean, rejected = _apply_checks(returns, "return_id", "returns", checks)
    clean["return_date"] = pd.to_datetime(clean["return_date"], format=config.DATE_FORMAT)
    return clean, rejected

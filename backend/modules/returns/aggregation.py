"""Deterministic counts and rates. Pure functions over clean DataFrames."""
import pandas as pd


def _rate(returns, orders):
    return (returns / orders.where(orders > 0)).round(4)


def overall_summary(orders: pd.DataFrame, returns: pd.DataFrame) -> dict:
    n_ret, n_ord = len(returns), len(orders)
    return {
        "total_orders": n_ord,
        "total_returns": n_ret,
        "return_rate": round(n_ret / n_ord, 4) if n_ord else 0.0,
        "dropdown_classified": int((returns["classification_source"] == "dropdown").sum()),
        "other_with_comment": int(returns["needs_llm"].sum()),
        "other_without_comment": int((returns["classification_source"] == "no_comment").sum()),
        "other_share": round(float((returns["return_reason"].str.lower() == "other").mean()), 4) if n_ret else 0.0,
    }


def by_dimension(orders: pd.DataFrame, returns: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Orders, returns and return rate grouped by one or more columns (e.g. ['product_id','size'])."""
    o = orders.groupby(cols).size().rename("orders")
    r = returns.groupby(cols).size().rename("returns")
    out = pd.concat([o, r], axis=1).fillna(0).astype(int)
    out["return_rate"] = _rate(out["returns"], out["orders"])
    return out.reset_index().sort_values("return_rate", ascending=False)


def reason_counts(returns: pd.DataFrame, by: list = None) -> pd.DataFrame:
    cols = (by or []) + ["primary_reason", "sub_reason"]
    g = returns.fillna({"sub_reason": "-"}).groupby(cols).size().rename("count").reset_index()
    return g.sort_values("count", ascending=False)


def product_table(orders: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    base = by_dimension(orders, returns, ["product_id", "product_name", "category"])
    pivot = (returns.groupby(["product_id", "primary_reason"]).size()
             .unstack(fill_value=0).add_prefix("n_").reset_index())
    return base.merge(pivot, on="product_id", how="left").fillna(0)

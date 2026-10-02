"""Deterministic normalization of size / colour / dropdown reason. No AI."""
import re
import pandas as pd
from . import config
from .validation import REJECT_COLUMNS


def norm_text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def normalize_size(v):
    return config.SIZE_MAP.get(norm_text(v))


def normalize_colour(v):
    return config.COLOUR_MAP.get(norm_text(v))


def map_dropdown_reason(v):
    """-> (primary, sub) for known dropdown values, else None."""
    return config.DROPDOWN_REASON_MAP.get(norm_text(v))


def _reject_rows(df, id_col, source, mask, reason):
    rows = [{"source": source, "record_id": df.at[i, id_col], "reason": reason} for i in df.index[mask]]
    return pd.DataFrame(rows, columns=REJECT_COLUMNS)


def normalize_orders(orders: pd.DataFrame):
    df = orders.copy()
    df["size"] = df["size"].map(normalize_size)
    df["colour"] = df["colour"].map(normalize_colour).fillna("UNKNOWN")
    bad = df["size"].isna()
    return df[~bad].copy(), _reject_rows(df, "order_id", "orders", bad, "unknown_size")


def normalize_returns(returns: pd.DataFrame):
    """Adds primary_reason / sub_reason / body_area / classification_source / needs_llm."""
    df = returns.copy()
    df["size"] = df["size"].map(normalize_size)
    df["colour"] = df["colour"].map(normalize_colour).fillna("UNKNOWN")
    bad_size = df["size"].isna()
    rejected = _reject_rows(df, "return_id", "returns", bad_size, "unknown_size")
    df = df[~bad_size].copy()

    mapped = df["return_reason"].map(map_dropdown_reason)
    is_other = df["return_reason"].map(norm_text) == config.OTHER_REASON
    unknown_reason = mapped.isna() & ~is_other
    rejected = pd.concat(
        [rejected, _reject_rows(df, "return_id", "returns", unknown_reason, "unknown_return_reason")],
        ignore_index=True,
    )
    keep = ~unknown_reason
    df, mapped, is_other = df[keep].copy(), mapped[keep], is_other[keep]

    df["return_comment"] = df["return_comment"].fillna("").str.strip()
    has_comment = df["return_comment"] != ""

    df["primary_reason"] = mapped.map(lambda t: t[0] if isinstance(t, tuple) else None)
    df["sub_reason"] = mapped.map(lambda t: t[1] if isinstance(t, tuple) else None)
    df["body_area"] = None
    df["classification_source"] = "dropdown"

    # "Other" + comment -> needs language understanding later; "Other" + blank -> nothing to analyse
    pending = is_other & has_comment
    no_comment = is_other & ~has_comment
    df.loc[pending, "primary_reason"] = "UNCLASSIFIED"
    df.loc[pending, "classification_source"] = "pending_llm"
    df.loc[no_comment, "primary_reason"] = "UNSPECIFIED"
    df.loc[no_comment, "sub_reason"] = "NO_COMMENT"
    df.loc[no_comment, "classification_source"] = "no_comment"
    df["needs_llm"] = pending
    return df, rejected

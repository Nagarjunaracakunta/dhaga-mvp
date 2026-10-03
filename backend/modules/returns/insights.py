"""Rule-based candidate insights. Code decides WHAT is notable; a later LLM only explains it."""
import pandas as pd
from . import config

DIMENSIONS = {
    "product": ["product_id"],
    "product_size": ["product_id", "size"],
    "product_colour": ["product_id", "colour"],
}


def find_candidate_insights(orders, returns, min_returns=config.MIN_RETURNS_FOR_INSIGHT,
                            lift_threshold=config.LIFT_THRESHOLD) -> list:
    if orders.empty or returns.empty:
        return []
    baseline = len(returns) / len(orders)
    names = orders.drop_duplicates("product_id").set_index("product_id")["product_name"]
    prod_rate = (returns.groupby("product_id").size() / orders.groupby("product_id").size()).fillna(0)
    out = []
    for dim, cols in DIMENSIONS.items():
        o = orders.groupby(cols).size().rename("orders")
        r = returns.groupby(cols).size().rename("returns")
        cells = pd.concat([o, r], axis=1).fillna(0).astype(int).reset_index()
        cells["rate"] = cells["returns"] / cells["orders"]
        cells["lift"] = cells["rate"] / baseline
        flagged = cells[(cells["returns"] >= min_returns) & (cells["lift"] >= lift_threshold)]
        if dim != "product":  # sub-segments must stand out from their own product, not just the shop average
            flagged = flagged[flagged["rate"] >= flagged["product_id"].map(prod_rate) * config.PARENT_LIFT_THRESHOLD]
        for _, c in flagged.iterrows():
            mask = pd.Series(True, index=returns.index)
            for col in cols:
                mask &= returns[col] == c[col]
            sub = returns[mask]
            breakdown = sub["primary_reason"].value_counts()
            comments = sub.loc[sub["needs_llm"], "return_comment"].head(config.MAX_SAMPLE_COMMENTS).tolist()
            out.append({
                "insight_id": f"{dim}:" + "|".join(str(c[col]) for col in cols),
                "dimension": dim,
                "product_id": c["product_id"],
                "product_name": names.get(c["product_id"]),
                "segment": {col: c[col] for col in cols if col != "product_id"},
                "orders": int(c["orders"]),
                "returns": int(c["returns"]),
                "return_rate": round(float(c["rate"]), 4),
                "baseline_rate": round(baseline, 4),
                "lift": round(float(c["lift"]), 2),
                "reason_breakdown": {k: int(v) for k, v in breakdown.items()},
                "unclassified_share": round(float((sub["classification_source"] == "pending_llm").mean()), 4),
                "sample_comments": comments,
            })
    return sorted(out, key=lambda x: x["lift"], reverse=True)

"""Orchestrates the pipeline: ingest -> validate -> normalize -> apply saved AI reasons -> aggregate -> insights.

Data comes from the demo CSVs (source="csv") or the live Supabase tables (source="supabase").
"""
from dataclasses import dataclass
import pandas as pd
from . import config, ingestion, validation, normalization, aggregation, insights
from .classifier import apply_classifications


@dataclass
class PipelineResult:
    products: pd.DataFrame
    orders: pd.DataFrame
    returns: pd.DataFrame
    rejected: pd.DataFrame
    summary: dict
    candidate_insights: list


def run_pipeline(data_dir=config.DATA_DIR, source: str = "csv", store=None) -> PipelineResult:
    if source == "supabase":
        from . import supabase_loader
        products, orders_raw, returns_raw = (supabase_loader.load_products(), supabase_loader.load_orders(),
                                             supabase_loader.load_returns())
        min_returns = config.MIN_RETURNS_FOR_INSIGHT_SUPABASE
    else:
        products = ingestion.load_products(data_dir)
        orders_raw = ingestion.load_orders(data_dir)
        returns_raw = ingestion.load_returns(data_dir)
        min_returns = config.MIN_RETURNS_FOR_INSIGHT

    orders, rej_o1 = validation.validate_orders(orders_raw, products)
    orders, rej_o2 = normalization.normalize_orders(orders)
    returns, rej_r1 = validation.validate_returns(returns_raw, orders, products)
    returns, rej_r2 = normalization.normalize_returns(returns)
    if store is not None:
        returns = store.overlay(returns)
    returns = apply_classifications(returns)

    # Catalogue is the source of truth for product name / category
    cat = products[[c for c in ["product_id", "product_name", "category", "sku"] if c in products.columns]]
    orders = orders.merge(cat, on="product_id", how="left")
    returns = returns.drop(columns=["product_name", "category"]).merge(cat, on="product_id", how="left")

    rejected = pd.concat([rej_o1, rej_o2, rej_r1, rej_r2], ignore_index=True)
    summary = aggregation.overall_summary(orders, returns)
    summary["raw_orders"] = len(orders_raw)
    summary["raw_returns"] = len(returns_raw)
    summary["rejected_records"] = len(rejected)
    src = returns["classification_source"]
    summary["other_with_comment"] = int(src.isin(["pending_llm", "ai", "ai_review", "human"]).sum())
    summary["other_pending"] = int((src == "pending_llm").sum())
    summary["ai_classified"] = int(src.isin(["ai", "ai_review"]).sum())
    summary["needs_review"] = int((src == "ai_review").sum())
    summary["human_reviewed"] = int((src == "human").sum())
    summary["data_source"] = source
    warnings = []
    if "order_status" in orders.columns:  # live data only
        status = returns["order_id"].map(orders.set_index("order_id")["order_status"])
        undelivered = int((status != "DELIVERED").sum())
        if undelivered:
            warnings.append(f"{undelivered} returns belong to orders that were never delivered "
                            "(a problem in the synthetic data; kept, not rejected)")
    summary["data_warnings"] = warnings
    found = insights.find_candidate_insights(orders, returns, min_returns=min_returns)
    return PipelineResult(products, orders, returns, rejected, summary, found)


def save_processed(res: PipelineResult, out_dir=config.PROCESSED_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    res.returns.to_csv(out_dir / "returns_clean.csv", index=False)
    res.orders.to_csv(out_dir / "orders_clean.csv", index=False)
    res.rejected.to_csv(out_dir / "rejected_records.csv", index=False)


def print_report(res: PipelineResult):
    print("=== SUMMARY ===")
    for k, v in res.summary.items():
        print(f"{k:24} {v}")
    print("\n=== REJECTED (by reason) ===")
    print(res.rejected.groupby(["source", "reason"]).size().to_string())
    print("\n=== RETURN RATE BY PRODUCT ===")
    print(aggregation.by_dimension(res.orders, res.returns, ["product_id", "product_name"]).to_string(index=False))
    print("\n=== CANDIDATE INSIGHTS ===")
    for i in res.candidate_insights:
        seg = ", ".join(f"{k}={v}" for k, v in i["segment"].items()) or "whole product"
        print(f"- {i['product_name']} [{seg}]  returns={i['returns']}/{i['orders']}  "
              f"rate={i['return_rate']:.1%}  lift={i['lift']}x  unclassified={i['unclassified_share']:.0%}")


if __name__ == "__main__":
    result = run_pipeline()
    save_processed(result)
    print_report(result)

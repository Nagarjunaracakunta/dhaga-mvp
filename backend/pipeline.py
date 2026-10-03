"""Orchestrates the no-AI pipeline: ingest -> validate -> normalize -> aggregate -> insights."""
from dataclasses import dataclass
import pandas as pd
from . import config, ingestion, validation, normalization, aggregation, insights


@dataclass
class PipelineResult:
    products: pd.DataFrame
    orders: pd.DataFrame
    returns: pd.DataFrame
    rejected: pd.DataFrame
    summary: dict
    candidate_insights: list


def run_pipeline(data_dir=config.DATA_DIR) -> PipelineResult:
    products = ingestion.load_products(data_dir)
    orders_raw = ingestion.load_orders(data_dir)
    returns_raw = ingestion.load_returns(data_dir)

    orders, rej_o1 = validation.validate_orders(orders_raw, products)
    orders, rej_o2 = normalization.normalize_orders(orders)
    returns, rej_r1 = validation.validate_returns(returns_raw, orders, products)
    returns, rej_r2 = normalization.normalize_returns(returns)

    # Catalogue is the source of truth for product name / category
    cat = products[["product_id", "product_name", "category"]]
    orders = orders.merge(cat, on="product_id", how="left")
    returns = returns.drop(columns=["product_name", "category"]).merge(cat, on="product_id", how="left")

    rejected = pd.concat([rej_o1, rej_o2, rej_r1, rej_r2], ignore_index=True)
    summary = aggregation.overall_summary(orders, returns)
    summary["raw_orders"] = len(orders_raw)
    summary["raw_returns"] = len(returns_raw)
    summary["rejected_records"] = len(rejected)
    summary["returns_unknown_size"] = int((returns["size"] == "UNKNOWN").sum())
    summary["returns_unknown_colour"] = int((returns["colour"] == "UNKNOWN").sum())
    found = insights.find_candidate_insights(orders, returns)
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

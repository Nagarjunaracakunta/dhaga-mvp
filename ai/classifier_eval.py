"""Measure classifier quality against data/returns_ground_truth.csv (demo data only)."""
import pandas as pd

from backend import config as bconfig

LLM_SOURCES = {"llm", "llm_escalated", "cache", "rule", "llm_low_confidence", "llm_failed"}


def evaluate(classified: pd.DataFrame) -> dict:
    path = bconfig.DATA_DIR / "returns_ground_truth.csv"
    if not path.exists():
        return {"error": "ground truth file not found"}
    truth = pd.read_csv(path, keep_default_na=False)
    df = classified[classified["classification_source"].isin(LLM_SOURCES)].merge(truth, on="return_id")
    if df.empty:
        return {"error": "no LLM-classified rows to evaluate"}
    df["ok_primary"] = df["primary_reason"] == df["true_primary"]
    df["ok_full"] = df["ok_primary"] & (df["sub_reason"].fillna("") == df["true_sub"])
    trusted = df[~df["classification_source"].isin(["llm_low_confidence", "llm_failed"])]
    fit = trusted[trusted["true_primary"] == "FIT"]
    mism = (df[~df["ok_primary"]].groupby(["true_primary", "primary_reason"]).size()
            .sort_values(ascending=False).head(5))
    return {
        "rows_evaluated": len(df),
        "primary_accuracy_all": round(float(df["ok_primary"].mean()), 3),
        "primary+sub_accuracy_all": round(float(df["ok_full"].mean()), 3),
        "trusted_share": round(len(trusted) / len(df), 3),
        "primary_accuracy_trusted": round(float(trusted["ok_primary"].mean()), 3) if len(trusted) else None,
        "body_area_accuracy_on_fit": round(float((fit["body_area"].fillna("") == fit["true_body_area"]).mean()), 3) if len(fit) else None,
        "top_mismatches": {f"true={a} -> got={b}": int(n) for (a, b), n in mism.items()},
    }

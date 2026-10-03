"""Code takes over again: write validated classifications back into the returns table."""
import pandas as pd
from . import config
from .classifier import normalize_comment


def apply_classifications(returns: pd.DataFrame, results: dict, threshold=config.CONFIDENCE_THRESHOLD):
    df = returns.copy()
    df["confidence"] = 1.0
    df["llm_primary"] = None
    df["llm_sub"] = None
    counts = {"applied": 0, "low_confidence": 0, "failed": 0, "still_pending": 0}
    for i in df.index[df["needs_llm"]]:
        res = results.get(normalize_comment(df.at[i, "return_comment"]))
        if res is None:
            counts["still_pending"] += 1
            continue
        df.at[i, "confidence"] = res.confidence
        df.at[i, "llm_primary"], df.at[i, "llm_sub"] = res.primary, res.sub
        if res.source == "failed":
            df.loc[i, ["primary_reason", "sub_reason", "classification_source"]] = ["UNCLEAR", "UNCLEAR", "llm_failed"]
            counts["failed"] += 1
        elif res.confidence < threshold:
            df.loc[i, ["primary_reason", "sub_reason", "classification_source"]] = ["UNCLEAR", "UNCLEAR", "llm_low_confidence"]
            counts["low_confidence"] += 1
        else:
            df.at[i, "primary_reason"], df.at[i, "sub_reason"] = res.primary, res.sub
            df.at[i, "body_area"] = None if res.body_area == "NONE" else res.body_area
            df.at[i, "classification_source"] = res.source
            counts["applied"] += 1
        df.at[i, "needs_llm"] = False
    return df, counts

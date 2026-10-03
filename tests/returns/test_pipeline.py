import pandas as pd
from backend.modules.returns import normalization as n, validation as v, aggregation as a
from backend.modules.returns.pipeline import run_pipeline


def test_size_normalization():
    assert [n.normalize_size(x) for x in ["M", "medium", " m ", "Medium", "xl", "Free Size"]] == \
           ["M", "M", "M", "M", "XL", "FREE"]
    assert n.normalize_size("XXXL-ish") is None


def test_colour_normalization():
    assert n.normalize_colour("PINKISH") == "Pink"
    assert n.normalize_colour("Navy  Blue") == "Blue"
    assert n.normalize_colour("sparkly") is None


def test_dropdown_mapping():
    assert n.map_dropdown_reason("Size too small") == ("FIT", "TOO_TIGHT")
    assert n.map_dropdown_reason("Other") is None


def test_other_with_and_without_comment():
    df = pd.DataFrame({
        "return_id": ["a", "b", "c"], "size": ["M", "M", "M"], "colour": ["Pink"] * 3,
        "return_reason": ["Other", "Other", "Size too small"],
        "return_comment": ["shoulders tight", "", ""],
        "product_name": ["x"] * 3, "category": ["y"] * 3,
    })
    out, rej = n.normalize_returns(df)
    assert rej.empty
    assert out["needs_llm"].tolist() == [True, False, False]
    assert out["classification_source"].tolist() == ["pending_llm", "no_comment", "dropdown"]


def test_validation_catches_bad_rows():
    products = pd.DataFrame({"product_id": ["P1"], "product_name": ["n"], "category": ["c"]})
    orders = pd.DataFrame({"order_id": ["O1"], "customer_id": ["C"], "product_id": ["P1"],
                           "size": ["M"], "colour": ["Pink"], "order_date": ["2026-08-01"]})
    returns = pd.DataFrame({
        "return_id": ["R1", "R2", "R3", "R3"], "order_id": ["O1", "O1", "O1", "O1"],
        "product_id": ["P1", "P1", "", "P1"], "return_reason": ["Other"] * 4,
        "return_date": ["2026-08-05", "05/08/2026", "2026-08-05", "2026-08-05"],
    })
    clean, rej = v.validate_returns(returns, orders, products)
    assert clean["return_id"].tolist() == ["R1"] or clean["return_id"].tolist() == ["R1", "R3"]
    reasons = dict(zip(rej["record_id"] + rej["reason"], rej["reason"]))
    assert "R2invalid_return_date" in reasons and "R3missing_product_id" in reasons


def test_return_rate_math():
    orders = pd.DataFrame({"product_id": ["A"] * 10 + ["B"] * 10})
    returns = pd.DataFrame({"product_id": ["A"] * 3 + ["B"]})
    t = a.by_dimension(orders, returns, ["product_id"]).set_index("product_id")
    assert t.loc["A", "return_rate"] == 0.3 and t.loc["B", "return_rate"] == 0.1


def test_end_to_end_surfaces_planted_patterns():
    res = run_pipeline()
    assert res.summary["rejected_records"] >= 9
    ids = [i["insight_id"] for i in res.candidate_insights]
    assert "product_size:SKU4421|L" in ids
    assert "product_colour:SKU4450|Mustard" in ids
    assert res.returns["return_id"].is_unique

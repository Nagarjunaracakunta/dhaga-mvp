"""Returns Insights API. Mounted at /api/returns."""
import json
from typing import Optional

from fastapi import APIRouter, Query

from . import aggregation
from .pipeline import run_pipeline

router = APIRouter(tags=["returns"])
_cache = {}


def _result(refresh: bool = False):
    if refresh or "res" not in _cache:
        _cache["res"] = run_pipeline()
    return _cache["res"]


def _records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


@router.get("/summary")
def summary(refresh: bool = False):
    return _result(refresh).summary


@router.get("/products")
def products():
    r = _result()
    return _records(aggregation.product_table(r.orders, r.returns))


@router.get("/breakdown")
def breakdown(by: str = Query("size", pattern="^(size|colour|category|product_id)$")):
    r = _result()
    return _records(aggregation.by_dimension(r.orders, r.returns, [by]))


@router.get("/reasons")
def reasons(product_id: Optional[str] = None):
    r = _result()
    df = r.returns if not product_id else r.returns[r.returns["product_id"] == product_id]
    return _records(aggregation.reason_counts(df))


@router.get("/insights")
def candidate_insights():
    return _result().candidate_insights


@router.get("/records")
def records(
    needs_llm: Optional[bool] = None,
    product_id: Optional[str] = None,
    limit: int = 100
):
    df = _result().returns
    if needs_llm is not None:
        df = df[df["needs_llm"] == needs_llm]
    if product_id:
        df = df[df["product_id"] == product_id]
    return _records(df.head(limit))


@router.get("/rejected")
def rejected():
    return _records(_result().rejected)

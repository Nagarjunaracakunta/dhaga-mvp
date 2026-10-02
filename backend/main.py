"""Thin FastAPI layer over the pipeline. Run: uvicorn backend.main:app --reload"""
import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from . import aggregation
from .pipeline import run_pipeline
from typing import Optional

app = FastAPI(title="Dhaga Returns Insights (no-AI baseline)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_cache = {}


def _result(refresh: bool = False):
    if refresh or "res" not in _cache:
        _cache["res"] = run_pipeline()
    return _cache["res"]


def _records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


@app.get("/api/summary")
def summary(refresh: bool = False):
    return _result(refresh).summary


@app.get("/api/products")
def products():
    r = _result()
    return _records(aggregation.product_table(r.orders, r.returns))


@app.get("/api/breakdown")
def breakdown(by: str = Query("size", pattern="^(size|colour|category|product_id)$")):
    r = _result()
    return _records(aggregation.by_dimension(r.orders, r.returns, [by]))


@app.get("/api/reasons")
def reasons(product_id: Optional[str] = None):
    r = _result()
    df = r.returns if not product_id else r.returns[r.returns["product_id"] == product_id]
    return _records(aggregation.reason_counts(df))


@app.get("/api/insights")
def candidate_insights():
    return _result().candidate_insights


@app.get("/api/returns")
def returns(
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


@app.get("/api/rejected")
def rejected():
    return _records(_result().rejected)

"""Dhaga returns insights: the reviewer app.   Run:  streamlit run app.py

Flow for Neha: pick data -> Run analysis -> read ranked briefs -> approve / dismiss / follow up (saved to the database).
Anything the system could not do is shown on screen (tab "What it could not do"), never hidden.
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from ai.classifier import classify_comments
from ai.config import CONFIDENCE_THRESHOLD
from ai.cost import CostTracker
from ai.estimate import weekly_cost
from ai.llm import AuthError, ModelSpec, check_credentials, specs_from_env
from ai.run import run
from backend import config as bconfig
from db import store

st.set_page_config(page_title="Dhaga returns insights", page_icon="🧵", layout="wide")

MOCK = ModelSpec("mock", "mock")
REVIEW_LABELS = {"approved": "Approve", "needs_followup": "Needs follow-up", "dismissed": "Dismiss"}
STATUS_ICON = {"pending": "🕓", "approved": "✅", "needs_followup": "🔎", "dismissed": "🚫"}


# ---------------------------------------------------------------- helpers
def get_engine():
    if "engine" not in st.session_state:
        eng = store.get_engine()
        store.init_schema(eng)
        st.session_state["engine"] = eng
    return st.session_state["engine"]


def prepare_data_dir(uploads: dict) -> Path:
    """Demo CSVs, overridden by whatever the user uploaded."""
    d = Path(tempfile.mkdtemp(prefix="dhaga_"))
    for name in ("products", "orders", "returns"):
        up = uploads.get(name)
        (d / f"{name}.csv").write_bytes(up.getvalue() if up else (bconfig.DATA_DIR / f"{name}.csv").read_bytes())
    return d


def pct(x):
    return f"{x * 100:.1f}%"


# ---------------------------------------------------------------- sidebar
st.sidebar.title("🧵 Dhaga returns")
live = st.sidebar.radio("Models", ["Offline demo (free, rule-based)", "Live models (OpenRouter)"]) .startswith("Live")
if live:
    fast, strong, fallback = specs_from_env()
    st.sidebar.caption(f"fast: `{fast.label}`  \nstrong: `{strong.label}`")
else:
    fast, strong, fallback = MOCK, MOCK, None
    st.sidebar.caption("Offline mode uses simple keyword rules, not a model. Good for trying the screens, not for judging accuracy.")

source = st.sidebar.radio("Data", ["Demo data", "Upload CSVs"])
uploads = {}
if source == "Upload CSVs":
    st.sidebar.caption("Any file you skip falls back to the demo file.")
    for name, cols in {"returns": "return_id, order_id, product_id, size, colour, return_reason, return_comment, return_date",
                       "orders": "order_id, customer_id, product_id, size, colour, order_date",
                       "products": "product_id, product_name, category"}.items():
        uploads[name] = st.sidebar.file_uploader(f"{name}.csv", type="csv", help=f"Columns: {cols}")
limit = st.sidebar.number_input("Max distinct comments to send to the model", 10, 5000, 60, step=10, disabled=not live,
                                help="Keeps a first live run cheap. The rest stay 'pending' and are reported.")
max_usd = st.sidebar.number_input("Budget cap (USD)", 0.05, 20.0, 0.50, step=0.05, disabled=not live)

if st.sidebar.button("Run analysis", type="primary"):
    try:
        if live:
            check_credentials(fast, strong)
        data_dir = prepare_data_dir(uploads) if source == "Upload CSVs" else bconfig.DATA_DIR
        with st.spinner("Cleaning data, reading comments, writing briefs..."):
            _, _, rep = run(fast, strong, fallback, limit=int(limit) if live else None, max_usd=float(max_usd),
                            with_eval=(source == "Demo data"), engine=get_engine(), data_dir=data_dir)
        st.session_state["run_id"] = rep["run_id"]
        st.sidebar.success("Done.")
    except AuthError as e:
        st.error(f"Cannot use live models: {e}")
    except ValueError as e:
        st.error(f"Could not read the files: {e}")
    except Exception as e:  # fail visibly, never silently
        st.error(f"The run failed: {type(e).__name__}: {e}")

engine = get_engine()
run_id = st.session_state.get("run_id") or store.latest_run_id(engine)
st.sidebar.divider()
st.sidebar.caption(f"Storage: {engine.dialect.name}" + (" (local file, resets on most hosts)" if engine.dialect.name == "sqlite" else ""))

# ---------------------------------------------------------------- main
st.title("Which returns should we investigate first?")
if not run_id:
    st.info("No analysis yet. Choose data and click **Run analysis** in the sidebar.")
    st.stop()

report = store.get_run_report(engine, run_id) or {}
pipe, applied, cls = report.get("pipeline", {}), report.get("applied", {}), report.get("classification", {})
st.caption(f"Run `{run_id}` · models: {report.get('models', {}).get('fast')} / {report.get('models', {}).get('strong')}")

tab_briefs, tab_rates, tab_fail, tab_try, tab_cost = st.tabs(
    ["Briefs for review", "Return rates", "What it could not do", "Try a comment", "Run & cost"])

# ---- Briefs
with tab_briefs:
    recs = report.get("recommendations", {})
    c = st.columns(5)
    c[0].metric("Returns analysed", f"{pipe.get('total_returns', 0):,}")
    c[1].metric("'Other' returns with a comment", f"{pipe.get('other_with_comment', 0):,}")
    c[2].metric("Comments classified", f"{applied.get('applied', 0):,}")
    c[3].metric("Left as unclear", f"{applied.get('low_confidence', 0) + applied.get('failed', 0):,}",
                help="Too vague or too uncertain to trust. Shown, not guessed.")
    c[4].metric("Briefs needing manual check", recs.get("needs_manual_review", 0))
    if applied.get("still_pending"):
        st.warning(f"{applied['still_pending']} comments were not processed (budget or limit reached). They are NOT counted in any reason.")

    me = st.text_input("Your name (saved with your decision)", key="reviewer")
    rows = store.list_insights(engine, run_id)
    if not rows:
        st.info("No product or size stands out enough to flag in this data.")
    for r in rows:
        rec = r["recommendation"] or {}
        icon = STATUS_ICON.get(r["review_status"], "")
        title = f"{icon} {rec.get('headline', r['product_name'])}  ·  {pct(r['return_rate'])} returned ({r['lift']}x the average)"
        with st.expander(title, expanded=(r["review_status"] == "pending" and r is rows[0])):
            if r["status"] != "passed_checks":
                st.error("This brief did NOT pass the automated fact checks. Read the numbers yourself before using it: "
                         + "; ".join(r["open_issues"] or ["unknown issue"]))
            if rec:
                st.markdown(f"**{rec.get('explanation', '')}**")
                st.markdown(f"Suggested next step: {rec.get('suggested_action', '')}")
            ev = r["evidence"] or {}
            m = st.columns(4)
            m[0].metric("Orders", ev.get("orders")); m[1].metric("Returns", ev.get("returns"))
            m[2].metric("Return rate", f"{ev.get('return_rate_pct')}%"); m[3].metric("Overall rate", f"{ev.get('overall_return_rate_pct')}%")
            if ev.get("top_reasons"):
                st.dataframe(pd.DataFrame(ev["top_reasons"]), hide_index=True)
            if ev.get("body_areas"):
                st.caption("Body areas mentioned: " + ", ".join(f"{b['area'].lower()} ({b['count']})" for b in ev["body_areas"]))
            if ev.get("unclassified_share_pct"):
                st.caption(f"{ev['unclassified_share_pct']}% of this segment's returns are still unclassified.")
            if r.get("sample_comments"):
                st.markdown("**What customers wrote (examples):**")
                for t in r["sample_comments"]:
                    st.markdown(f"> {t}")
            st.divider()
            k = r["insight_id"]
            choice = st.radio("Your decision", list(REVIEW_LABELS), format_func=REVIEW_LABELS.get, horizontal=True, key=f"d_{k}",
                              index=list(REVIEW_LABELS).index(r["review_status"]) if r["review_status"] in REVIEW_LABELS else 0)
            note = st.text_area("Note (optional)", value=r["review_note"] or "", key=f"n_{k}")
            if st.button("Save decision", key=f"s_{k}"):
                store.set_review(engine, run_id, r["insight_id"], choice, me or None, note or None)
                st.rerun()
            if r["review_status"] != "pending":
                st.caption(f"Current: {r['review_status']} by {r['reviewer'] or 'unknown'}")

# ---- Rates
with tab_rates:
    bp = pd.DataFrame(report.get("by_product", []))
    if bp.empty:
        st.info("No data.")
    else:
        st.subheader("Return rate by product")
        st.bar_chart(bp.set_index("product_name")["return_rate"])
        st.dataframe(bp, hide_index=True)
        st.subheader("By size")
        st.dataframe(pd.DataFrame(report.get("by_size", [])), hide_index=True)

# ---- Failures, on purpose visible
with tab_fail:
    st.markdown("Everything the system skipped, could not read, or was not sure about is listed here.")
    st.subheader("Rows rejected before analysis")
    rej = pd.DataFrame(report.get("rejected_by_reason", []))
    if rej.empty:
        st.success("None.")
    else:
        st.dataframe(rej, hide_index=True)
        with st.expander("See the rejected records"):
            st.dataframe(pd.DataFrame(report.get("rejected_sample", [])), hide_index=True)
    st.subheader("Kept, but with missing detail")
    st.write(f"Unknown size: **{pipe.get('returns_unknown_size', 0)}** returns · Unknown colour: **{pipe.get('returns_unknown_colour', 0)}** returns")
    st.subheader("Comments the model was not sure about")
    unclear = store.get_returns(engine, primary_reason="UNCLEAR", limit=40)
    st.write(f"Marked **UNCLEAR** (confidence below {CONFIDENCE_THRESHOLD}, no real reason given, or the model call failed): "
             f"**{applied.get('low_confidence', 0) + applied.get('failed', 0)}** in this run plus vague ones like 'ok ok'.")
    if len(unclear):
        st.dataframe(unclear[["return_id", "product_name", "return_comment", "classification_source", "confidence"]],
                     hide_index=True)
    st.subheader("Skipped to protect the budget")
    skipped = cls.get("skipped_budget", 0) + cls.get("left_unprocessed_limit", 0)
    st.warning(f"{skipped} distinct comments were not sent to the model.") if skipped else st.success("None.")
    bad = [r for r in store.list_insights(engine, run_id) if r["status"] != "passed_checks"]
    st.subheader("Briefs that failed the fact check")
    st.warning(f"{len(bad)} brief(s) need a manual read: " + ", ".join(b["product_name"] for b in bad)) if bad else st.success("None.")

# ---- Try a comment (live failure demo)
with tab_try:
    st.markdown("Type a return comment, in English, Hindi or Hinglish, and see how it would be read.")
    txt = st.text_input("Comment", value="M size shoulders pe bahut tight hai")
    if st.button("Classify") and txt.strip():
        try:
            if live:
                check_credentials(fast, strong)
            res, _ = classify_comments([txt], fast, strong, CostTracker(max_calls=4, max_usd=0.05), cache=None, fallback=fallback)
            out = res.get(txt.strip().lower())
            if out is None:
                st.warning("Not processed.")
            else:
                trusted = out.confidence >= CONFIDENCE_THRESHOLD and out.source != "failed"
                st.write(f"**{out.primary} / {out.sub}**" + (f" · area: {out.body_area}" if out.body_area != "NONE" else "")
                         + f" · confidence {out.confidence:.2f} · via {out.source}")
                (st.success if trusted else st.error)(
                    "Counted in the analysis." if trusted else "Too uncertain: this would be shown as UNCLEAR, not counted as a reason.")
        except AuthError as e:
            st.error(f"Cannot use live models: {e}")
        except Exception as e:
            st.error(f"Failed: {type(e).__name__}: {e}")

# ---- Cost
with tab_cost:
    cost = report.get("cost", {})
    c = st.columns(3)
    c[0].metric("Model calls this run", cost.get("calls", 0))
    c[1].metric("Estimated cost (USD)", f"${cost.get('estimated_usd', 0):.4f}")
    c[2].metric("Cache hits", cls.get("cache_hits", 0))
    st.json({"classification": cls, "cost": cost, "recommendations": report.get("recommendations")}, expanded=False)
    if report.get("classifier_eval"):
        st.subheader("Accuracy on the demo data (ground truth available)")
        st.json(report["classifier_eval"], expanded=False)
        if not live:
            st.caption("Offline rules were written against the same templates as the demo data, so this number is not meaningful.")
    st.subheader("What one weekly run costs at Dhaga's volume")
    ef, es, _ = specs_from_env()
    st.code("\n".join(weekly_cost(ef, es)))
    st.caption("[brief] = stated in the case study, [assumed] = our estimate.")

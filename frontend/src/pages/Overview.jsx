import { useNavigate } from "react-router-dom";
import { ArrowRight, Bot, Inbox, Layers, MessageSquareText, PackageX, RotateCcw, Sparkles, TriangleAlert, Zap } from "lucide-react";
import { api } from "../api.js";
import { num, pct, useApi } from "../useApi.js";
import { Empty, ErrorBox, IntentPill, Panel, Skeleton, Stat, StatusPill } from "../components/ui.jsx";

const LOOP = [
  ["1 · Classify", "Haiku 4.5 reads the message (English or Hinglish) and picks the intent.", "model"],
  ["2 · Facts", "Code finds the order and works out delay, cancellability and return window.", "code"],
  ["3 · Rules", "Risky cases (RTO, lost parcel, unclear) go straight to a person.", "code"],
  ["4 · Draft", "Opus 5.5 writes the reply from the facts and the matching policy only.", "model"],
  ["5 · Check", "Every date, amount and number is checked against the order, then Haiku reviews.", "code + model"],
  ["6 · Decide", "The agent approves, edits or escalates. Nothing is sent without them.", "human"],
];
const TONE = { model: "pink", code: "violet", "code + model": "violet", human: "green" };

export default function Overview({ onDemo }) {
  const navigate = useNavigate();
  const cx = useApi(() => api.cxMetrics(), []);
  const open = useApi(() => api.tickets({ status: "OPEN", limit: 5 }), []);
  const summary = useApi(() => api.returnsSummary(), []);
  const insights = useApi(() => api.returnsInsights(), []);

  const byStatus = cx.data?.tickets_by_status ?? {};
  const s = summary.data;

  return (
    <div className="grid">
      <section className="panel hero">
        <div className="left">
          <div className="ico"><Sparkles size={22} color="#fff" /></div>
          <div>
            <h1>CX Copilot &amp; Returns Insights <span className="pill green"><span className="dot" /> Active</span></h1>
            <p>58% of support tickets ask "where is my order". 44% of returns say "Other". This workbench handles both.</p>
          </div>
        </div>
        <button className="btn hot" onClick={onDemo}><Zap size={15} /> Launch 1-Click Demo</button>
      </section>

      <div className="grid stats">
        <Stat label="Open tickets" value={num((byStatus.OPEN ?? 0) + (byStatus.DRAFTED ?? 0))} sub={`${byStatus.DRAFTED ?? 0} with a draft ready`} icon={Inbox} loading={cx.loading} />
        <Stat label="Resolved" value={num(byStatus.RESOLVED ?? 0)} sub={`${byStatus.ESCALATED ?? 0} escalated to a person`} icon={MessageSquareText} tone="green" loading={cx.loading} />
        <Stat label="Return rate" value={pct(s?.return_rate)} sub={s ? `${num(s.total_returns)} of ${num(s.total_orders)} orders` : ""} icon={RotateCcw} tone="red" loading={summary.loading} />
        <Stat label='"Other" with comment' value={num(s?.other_with_comment)} sub="Waiting for AI classification" icon={Bot} tone="amber" loading={summary.loading} />
        <Stat label="Flagged segments" value={num(insights.data?.length)} sub="Products, sizes or colours returned too often" icon={TriangleAlert} tone="pink" loading={insights.loading} />
      </div>

      <div className="grid two">
        <Panel icon={Layers} title="How Copilot answers a ticket" subtitle="Models for language, code for facts, people for the final call">
          <div className="steps-list">
            {LOOP.map(([n, t, who]) => (
              <div className="step-row" key={n}>
                <span className="n">{n}</span>
                <span className="t">{t}</span>
                <span className={`pill ${TONE[who]}`}>{who}</span>
              </div>
            ))}
          </div>
        </Panel>

        <div className="grid">
          <Panel icon={Inbox} title="Waiting in the inbox" subtitle="Open tickets, oldest first"
            actions={<button className="btn sm" onClick={() => navigate("/cx")}>Open inbox <ArrowRight size={13} /></button>}>
            {open.loading ? <Skeleton rows={4} height={36} />
              : open.error ? <ErrorBox error={open.error} onRetry={open.reload} />
              : open.data.length === 0 ? <Empty title="Inbox clear">No open tickets right now.</Empty>
              : <div className="rowlist">
                  {open.data.map((t) => (
                    <button key={t.ticket_id} className="rowlink" onClick={() => navigate(`/cx?t=${t.ticket_number}`)}>
                      <span className="main">{t.customer_name} <span className="dim mono" style={{ fontWeight: 400 }}>{t.ticket_number}</span></span>
                      <span className="side"><StatusPill status={t.status} /> <IntentPill intent={t.last_intent} /></span>
                      <span className="sub">{t.message}</span>
                    </button>
                  ))}
                </div>}
          </Panel>

          <Panel icon={PackageX} title="Top return problems" subtitle="Highest lift over the shop average"
            actions={<button className="btn sm" onClick={() => navigate("/returns")}>All returns <ArrowRight size={13} /></button>}>
            {insights.loading ? <Skeleton rows={4} height={36} />
              : insights.error ? <ErrorBox error={insights.error} onRetry={insights.reload} />
              : <div className="rowlist">
                  {insights.data.slice(0, 4).map((i) => (
                    <button key={i.insight_id} className="rowlink" onClick={() => navigate(`/returns?segment=${encodeURIComponent(i.insight_id)}`)}>
                      <span className="main">{i.product_name} · {Object.values(i.segment).join(", ") || "whole product"}</span>
                      <span className="side"><b style={{ color: "var(--pink)", fontSize: 16 }}>{i.lift}×</b></span>
                      <span className="sub">{i.returns} of {i.orders} returned ({pct(i.return_rate)}) · {pct(i.unclassified_share, 0)} unclassified</span>
                    </button>
                  ))}
                </div>}
          </Panel>
        </div>
      </div>
    </div>
  );
}

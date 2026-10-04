import { useNavigate } from "react-router-dom";
import { ArrowRight, Bot, ClipboardCheck, Inbox, MessageSquareText, PackageX, RotateCcw, TriangleAlert, Zap } from "lucide-react";
import { api } from "../api.js";
import { num, pct, useApi } from "../useApi.js";
import { Empty, ErrorBox, PageHeader, Panel, Skeleton, Stat, StatusPill } from "../components/ui.jsx";

const STEPS = [
  ["Classify", "Haiku reads the message, English or Hinglish, and picks the intent."],
  ["Facts", "Code finds the order and works out delay and return window."],
  ["Rules", "Risky cases (RTO, lost parcel, unclear) go to a person."],
  ["Draft", "Opus writes the reply from the facts and policy only."],
  ["Check", "Every date and amount is checked against the order."],
  ["Decide", "The agent approves, edits or escalates."],
];

const CATEGORY = { FIT: "Fit", COLOUR: "Colour", QUALITY: "Quality", DAMAGE: "Damage", WRONG_ITEM: "Wrong item", CHANGED_MIND: "Changed mind", UNCLEAR: "Unclear" };

export default function Overview({ onDemo }) {
  const navigate = useNavigate();
  const cx = useApi(() => api.cxMetrics(), []);
  const counts = useApi(() => api.inbox({ limit: 1 }).then((p) => p.counts), []);
  const open = useApi(() => api.inbox({ view: "open", sort: "priority", limit: 6 }).then((p) => p.items), []);
  const review = useApi(() => api.returnsReviewQueue({ limit: 6 }), []);
  const summary = useApi(() => api.returnsSummary(), []);
  const insights = useApi(() => api.returnsInsights(), []);

  const byStatus = cx.data?.tickets_by_status ?? {};
  const s = summary.data;

  return (
    <>
      <PageHeader
        title="Good to see you. Here's what needs you."
        subtitle={`58% of support tickets ask "where is my order", and 44% of returns just say "Other". Copilot drafts the first; AI explains the second. You make the call on both.`}
        actions={<button className="btn hot" onClick={onDemo}><Zap size={15} /> Run the demo</button>}
      />

      <div className="grid stats">
        <Stat label="Open tickets" value={num(counts.data?.open)} sub={`+ ${num(counts.data?.needs_person ?? 0)} need a person · ${num(counts.data?.drafted ?? 0)} drafts ready`} icon={Inbox} loading={counts.loading} />
        <Stat label="Resolved" value={num(byStatus.RESOLVED ?? 0)} sub={`${num(byStatus.ESCALATED ?? 0)} escalated to a person`} icon={MessageSquareText} tone="green" loading={cx.loading} />
        <Stat label="Return rate" value={pct(s?.return_rate)} sub={s ? `${num(s.total_returns)} of ${num(s.total_orders)} orders` : ""} icon={RotateCcw} tone="red" loading={summary.loading} />
        <Stat label='"Other" with a comment' value={num(s?.other_with_comment)} sub="Explained by AI, checked by people" icon={Bot} tone="amber" loading={summary.loading} />
        <Stat label="Flagged segments" value={num(insights.data?.length)} sub="Returned 1.5× the shop average or more" icon={TriangleAlert} tone="cyan" loading={insights.loading} />
      </div>

      <div className="grid three">
        <Panel icon={Inbox} title="Tickets waiting" subtitle={counts.data ? `Top of the ${num(counts.data.open)} open tickets, most urgent first` : "Open, most urgent first"} bodyClass=""
          actions={<button className="btn sm" onClick={() => navigate("/cx")}>Inbox <ArrowRight size={13} /></button>}>
          {open.loading ? <div className="panel-body"><Skeleton rows={4} height={36} /></div>
            : open.error ? <div className="panel-body"><ErrorBox error={open.error} onRetry={open.reload} /></div>
            : open.data.length === 0 ? <Empty title="Inbox clear">No open tickets right now.</Empty>
            : <div className="rowlist">
                {open.data.map((t) => (
                  <button key={t.ticket_id} className="rowlink" onClick={() => navigate(`/cx?t=${t.ticket_number}`)}>
                    <span className="main">{t.customer_name}</span>
                    <span className="side">
                      {t.days_late >= 7 && <span className="pill red">{num(t.days_late)} days late</span>}
                      {t.repeat_count > 1 && <span className="pill amber">Asked {t.repeat_count}×</span>}
                      {t.days_late < 7 && t.repeat_count < 2 && <StatusPill status={t.status} />}
                    </span>
                    <span className="sub">{t.message}</span>
                  </button>
                ))}
              </div>}
        </Panel>

        <Panel icon={ClipboardCheck} title="Return reasons to check" subtitle="AI wasn't sure, so a person decides" bodyClass=""
          actions={<button className="btn sm" onClick={() => navigate("/returns")}>Review <ArrowRight size={13} /></button>}>
          {review.loading ? <div className="panel-body"><Skeleton rows={4} height={36} /></div>
            : review.error ? <div className="panel-body"><ErrorBox error={review.error} onRetry={review.reload} /></div>
            : review.data.length === 0 ? <Empty icon={ClipboardCheck} title="Nothing to check">Run a classification on the Returns page to fill this queue.</Empty>
            : <div className="rowlist">
                {review.data.map((r) => (
                  <button key={r.return_id} className="rowlink" onClick={() => navigate("/returns")}>
                    <span className="main">"{r.return_comment}"</span>
                    <span className="side"><span className="pill amber">{CATEGORY[r.ai_category] ?? r.ai_category} · {pct(r.ai_confidence, 0)}</span></span>
                    <span className="sub">{r.product_name} · {[r.size, r.colour].filter(Boolean).join(", ")}</span>
                  </button>
                ))}
              </div>}
        </Panel>

        <Panel icon={PackageX} title="Products returned too often" subtitle="Highest lift over the shop average" bodyClass=""
          actions={<button className="btn sm" onClick={() => navigate("/returns")}>All <ArrowRight size={13} /></button>}>
          {insights.loading ? <div className="panel-body"><Skeleton rows={4} height={36} /></div>
            : insights.error ? <div className="panel-body"><ErrorBox error={insights.error} onRetry={insights.reload} /></div>
            : insights.data.length === 0 ? <Empty title="No flagged products" />
            : <div className="rowlist">
                {insights.data.slice(0, 6).map((i) => (
                  <button key={i.insight_id} className="rowlink" onClick={() => navigate(`/returns?segment=${encodeURIComponent(i.insight_id)}`)}>
                    <span className="main">{i.product_name}</span>
                    <span className="side"><b style={{ color: "var(--accent-ink)", fontFamily: "var(--display)", fontSize: 17 }}>{i.lift}×</b></span>
                    <span className="sub">{Object.values(i.segment).join(", ") || "Whole product"} · {i.returns} of {i.orders} returned</span>
                  </button>
                ))}
              </div>}
        </Panel>
      </div>

      <section>
        <div className="navgroup-label" style={{ color: "var(--muted)", padding: "0 0 8px" }}>How Copilot answers a ticket</div>
        <div className="steps-strip">
          {STEPS.map(([t, d], i) => (
            <div key={t}>
              <span className="n">{String(i + 1).padStart(2, "0")}</span>
              <span className="t">{t}</span>
              <span className="d">{d}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

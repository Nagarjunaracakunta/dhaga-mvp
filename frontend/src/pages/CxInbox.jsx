import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Inbox, MessageSquareText, Package, RefreshCw, Search, Sparkles, WandSparkles } from "lucide-react";
import { api } from "../api.js";
import { day, inr, label, time, useApi } from "../useApi.js";
import { CloseButton, Empty, ErrorBox, INTENT_TEXT, IntentPill, Overlay, Panel, Skeleton, StatusPill } from "../components/ui.jsx";
import CopilotPanel, { LoadingSteps } from "../components/CopilotPanel.jsx";
import { useToast } from "../components/Toast.jsx";

const STATUS_CHIPS = [["", "All"], ["OPEN", "Open"], ["DRAFTED", "Drafted"], ["RESOLVED", "Resolved"], ["ESCALATED", "Escalated"]];

export default function CxInbox() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const selected = params.get("t");
  const [status, setStatus] = useState("");
  const [intent, setIntent] = useState("");
  const [query, setQuery] = useState("");
  const [tryOpen, setTryOpen] = useState(false);

  const list = useApi(() => api.tickets({ status, limit: 200 }), [status]);
  const insights = useApi(() => api.returnsInsights().catch(() => []), []);

  const tickets = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list.data ?? []).filter((t) =>
      (!intent || t.last_intent === intent) &&
      (!q || [t.ticket_number, t.customer_name, t.message].some((s) => s?.toLowerCase().includes(q))));
  }, [list.data, intent, query]);

  // Select the first ticket when nothing is selected yet
  useEffect(() => {
    if (!selected && tickets.length) setParams({ t: tickets[0].ticket_number }, { replace: true });
  }, [selected, tickets, setParams]);

  return (
    <div className="inbox">
      <section className="panel inbox-list" aria-label="Tickets">
        <div className="filters">
          <div style={{ display: "flex", gap: 8 }}>
            <label className="search" style={{ flex: 1 }}>
              <Search size={15} className="dim" />
              <input id="ticket-search" placeholder="Search name, message, TKT…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <button className="btn sm" title="Reload" onClick={list.reload}><RefreshCw size={14} /></button>
          </div>
          <div className="chips" role="group" aria-label="Status">
            {STATUS_CHIPS.map(([v, l]) => (
              <button key={l} className="chip" aria-pressed={status === v} onClick={() => setStatus(v)}>{l}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select id="intent-filter" className="select" value={intent} onChange={(e) => setIntent(e.target.value)} style={{ flex: 1 }}>
              <option value="">All intents</option>
              {Object.entries(INTENT_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button className="btn sm" onClick={() => setTryOpen(true)}><WandSparkles size={14} /> Try Copilot</button>
          </div>
        </div>
        <div className="tickets">
          {list.loading && <div style={{ padding: 14 }}><Skeleton rows={6} height={46} /></div>}
          {list.error && <div style={{ padding: 14 }}><ErrorBox error={list.error} onRetry={list.reload} /></div>}
          {!list.loading && !list.error && tickets.length === 0 && (
            <Empty title="No tickets here">Try another filter, or clear the search.</Empty>
          )}
          {tickets.map((t) => (
            <button key={t.ticket_id} className="tk" aria-current={selected === t.ticket_number} onClick={() => setParams({ t: t.ticket_number })}>
              <span className="r1"><span className="who">{t.customer_name}</span><span>{t.channel} · {time(t.created_at)}</span></span>
              <span className="msg">{t.message}</span>
              <span className="tags">
                <span className="pill grey mono">{t.ticket_number}</span>
                <StatusPill status={t.status} />
                <IntentPill intent={t.last_intent} />
              </span>
            </button>
          ))}
        </div>
      </section>

      {selected
        ? <TicketView key={selected} ticketRef={selected} insights={insights.data ?? []} onChanged={list.reload} toast={toast} />
        : <Panel><Empty icon={Inbox} title="Select a ticket">Pick a ticket on the left to see the customer's message and order.</Empty></Panel>}

      {tryOpen && <TryCopilot onClose={() => setTryOpen(false)} />}
    </div>
  );
}

// Find the flagged returns segment for an item, e.g. "Floral Midi Dress (M, Pink)" -> size M, else the whole product.
function segmentFor(facts, insights) {
  if (!facts) return null;
  const matches = (i, item) => {
    if (!item.startsWith(i.product_name)) return false;
    const attrs = (item.match(/\(([^)]*)\)/)?.[1] ?? "").split(",").map((s) => s.trim().toLowerCase());
    return Object.values(i.segment).every((v) => attrs.includes(String(v).toLowerCase()));
  };
  const candidates = insights.filter((i) => facts.items.some((item) => matches(i, item)));
  const hit = candidates.find((i) => Object.keys(i.segment).length > 0) ?? candidates[0];
  if (!hit) return null;
  const seg = Object.entries(hit.segment).map(([k, v]) => `${k} ${v}`).join(", ") || "whole product";
  return { to: `/returns?segment=${encodeURIComponent(hit.insight_id)}`, label: `See ${hit.product_name} (${seg}) in Returns →` };
}

function TicketView({ ticketRef, insights, onChanged, toast }) {
  const detail = useApi(() => api.ticket(ticketRef), [ticketRef]);
  const [result, setResult] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState(null);

  if (detail.loading) return <Panel><Skeleton rows={6} height={22} /></Panel>;
  if (detail.error) return <Panel><ErrorBox error={detail.error} onRetry={detail.reload} /></Panel>;

  const { ticket, facts: linkedFacts } = detail.data;
  // Only show saved results made by this app's Copilot (seeded rows in Supabase have a different shape)
  const saved = detail.data.last_result;
  const shown = result ?? (saved?.classification ? saved : null);
  const facts = shown?.facts ?? linkedFacts;
  const closed = ticket.status === "RESOLVED" || ticket.status === "ESCALATED";

  async function analyze() {
    setAnalyzing(true);
    setRunError(null);
    try {
      const r = await api.analyze(ticket.ticket_number);
      setResult({ ...r, human_action: null });
      onChanged();
    } catch (e) {
      setRunError(e);
    } finally {
      setAnalyzing(false);
    }
  }

  async function decide(action, finalReply) {
    setBusy(true);
    try {
      const res = await api.decide(ticket.ticket_number, { interaction_id: shown.interaction_id, action, final_reply: finalReply });
      toast(`${ticket.ticket_number}: ${label(res.human_action)} · ticket ${res.ticket_status.toLowerCase()}`);
      setResult(null);
      await detail.reload();
      onChanged();
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="detail">
      <Panel>
        <div style={{ display: "grid", gap: 18 }}>
          <div className="ticket-head">
            <div>
              <h2>{ticket.customer_name} <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>· {ticket.city}</span></h2>
              <div className="meta-row">
                <span className="mono">{ticket.ticket_number}</span>
                <span>{ticket.channel}</span>
                <span>{day(ticket.created_at)} {time(ticket.created_at)}</span>
              </div>
            </div>
            <StatusPill status={ticket.status} />
          </div>
          <div className="bubble">{ticket.message}</div>
          {facts ? (
            <div style={{ display: "grid", gap: 10 }}>
              <div className="muted" style={{ fontSize: 12, fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
                <Package size={14} /> Order facts {shown?.facts && <span className="dim">(order Copilot used)</span>}
              </div>
              <dl className="facts">
                <div><dt>Order</dt><dd className="mono">{facts.order_number}</dd></div>
                <div><dt>Status</dt><dd>{label(facts.status)}</dd></div>
                <div><dt>Courier</dt><dd>{facts.courier ?? "Not assigned"}</dd></div>
                <div><dt>Tracking</dt><dd className="mono">{facts.tracking_number ?? "–"}</dd></div>
                <div><dt>Expected</dt><dd>{day(facts.expected_delivery)}</dd></div>
                <div><dt>{facts.is_delivered ? "Delivered" : "Delay"}</dt>
                  <dd className={facts.days_late ? "late" : ""}>
                    {facts.is_delivered ? day(facts.delivered_on) : facts.days_late ? `${facts.days_late} days late` : "On time"}
                  </dd></div>
                <div><dt>Payment</dt><dd>{facts.payment_mode} · {inr(facts.total_amount)}</dd></div>
                <div><dt>Items</dt><dd>{facts.items.join(", ")}</dd></div>
              </dl>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>No order is linked to this ticket. Copilot will look for one.</p>
          )}
        </div>
      </Panel>

      <Panel icon={Bot} title="Copilot" subtitle="Classify → order facts → rules → draft → check. You approve before anything is sent."
        actions={!closed && !analyzing && (
          <button className={shown ? "btn" : "btn primary"} onClick={analyze}>
            <Sparkles size={15} /> {shown ? "Analyse again" : "Analyse with Copilot"}
          </button>
        )}>
        {analyzing ? <LoadingSteps />
          : runError ? <ErrorBox error={runError} onRetry={analyze} />
          : shown ? <CopilotPanel result={shown} busy={busy} onDecide={closed ? undefined : decide} segmentLink={segmentFor(facts, insights)} />
          : <Empty icon={MessageSquareText} title="Not analysed yet">Copilot reads the message, finds the order, and drafts a reply for you to review.</Empty>}
      </Panel>
    </div>
  );
}

function TryCopilot({ onClose }) {
  const [message, setMessage] = useState("Order DHC100231 kab aayega? 5 din ho gaye");
  const [orderNumber, setOrderNumber] = useState("");
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  async function run(e) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      setResult(await api.analyzeText({ message, order_number: orderNumber || undefined }));
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  }

  return (
    <Overlay onClose={onClose} labelledBy="try-title">
      <div className="dhead">
        <div>
          <h2 id="try-title">Try Copilot</h2>
          <p className="muted" style={{ margin: "4px 0 0" }}>Paste any customer message. Hinglish works. Nothing is saved to a ticket.</p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <form onSubmit={run} style={{ display: "grid", gap: 12 }}>
        <label className="field" htmlFor="try-message">Customer message
          <textarea id="try-message" className="input" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} required />
        </label>
        <label className="field" htmlFor="try-order">Order number (optional)
          <input id="try-order" className="input mono" placeholder="DHC100488" value={orderNumber} onChange={(e) => setOrderNumber(e.target.value)} />
        </label>
        <button className="btn primary" disabled={running || !message.trim()} style={{ justifySelf: "start" }}>
          <Sparkles size={15} /> {running ? "Analysing…" : "Analyse"}
        </button>
      </form>
      {running && <LoadingSteps />}
      {error && <ErrorBox error={error} />}
      {result && !running && <CopilotPanel result={result} />}
    </Overlay>
  );
}

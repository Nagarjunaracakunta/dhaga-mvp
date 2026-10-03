import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCheck, CopyCheck, Repeat2, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "../api.js";
import { num, pct, useApi } from "../useApi.js";
import { Empty, ErrorBox, INTENT_TEXT, PageHeader, Panel, Skeleton } from "../components/ui.jsx";
import { useToast } from "../components/Toast.jsx";

const SIZES = [5, 10, 20];
const COST_PER_DRAFT = 0.0104; // measured, see docs/build-note.md

export default function RepeatedQuestions() {
  const toast = useToast();
  const q = useApi(() => api.bulkQueue(), []);
  const [size, setSize] = useState(10);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [runError, setRunError] = useState(null);

  async function draft() {
    setRunning(true);
    setRunError(null);
    try {
      setLastRun(await api.bulkDraft(size));
      await q.reload();
    } catch (e) {
      setRunError(e);
    } finally {
      setRunning(false);
    }
  }

  const d = q.data;
  const threshold = d ? pct(d.min_confidence, 0) : "75%";
  const waiting = d ? d.groups.reduce((n, g) => n + g.count, 0) : 0;

  return (
    <>
      <PageHeader
        title="Repeated questions"
        subtitle={`Most tickets ask the same few things. Copilot drafts them in a batch; only drafts it is at least ${threshold} sure about, that passed every fact check, are listed here by question. You approve them group by group. Nothing goes to a customer until you do.`}
      />

      <Panel icon={Sparkles} title="Draft open tickets in a batch"
        subtitle={d ? `${num(d.open_tickets)} open tickets · oldest first · about $${COST_PER_DRAFT.toFixed(2)} per drafted ticket` : "Oldest open tickets first"}
        actions={
          <div className="actions" style={{ alignItems: "center" }}>
            <div className="seg-toggle" role="group" aria-label="Batch size">
              {SIZES.filter((n) => !d || n <= d.max_per_run).map((n) => (
                <button key={n} aria-pressed={size === n} onClick={() => setSize(n)}>{n} tickets</button>
              ))}
            </div>
            <button className="btn primary" disabled={running} onClick={draft}>
              <Sparkles size={15} /> {running ? `Drafting ${size} tickets…` : `Draft ${size} tickets`}
            </button>
          </div>
        }>
        {runError ? <ErrorBox error={runError} onRetry={draft} />
          : lastRun ? (
            <div className="callout green">
              <CheckCheck size={18} />
              <p><b>{lastRun.ready} of {lastRun.analysed} drafts are ready for group review</b>
                {lastRun.needs_person} went to a person (risky or unclear), {lastRun.below_threshold} drafted below {threshold} confidence
                {lastRun.failed ? `, ${lastRun.failed} failed` : ""}: those stay in the inbox for one-by-one review. Cost ${lastRun.cost_usd.toFixed(3)}.</p>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              Every ticket goes through the full Copilot workflow: lost parcels, damage and unclear messages still go to a person, and every date and amount is checked against the order.
            </p>
          )}
      </Panel>

      {q.loading ? <Panel><Skeleton rows={4} height={60} /></Panel>
        : q.error ? <ErrorBox error={q.error} onRetry={q.reload} />
        : waiting === 0 ? (
          <Panel>
            <Empty icon={CopyCheck} title="No drafts waiting for group review">
              Draft a batch above. Confident drafts land here, grouped by question.
            </Empty>
          </Panel>
        ) : d.groups.map((g) => <Group key={g.intent} group={g} toast={toast} onDone={q.reload} />)}
    </>
  );
}

function Group({ group, toast, onDone }) {
  const [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const all = picked.size === group.items.length;

  const toggle = (t) => setPicked((s) => {
    const n = new Set(s);
    n.has(t) ? n.delete(t) : n.add(t);
    return n;
  });

  async function approve() {
    setBusy(true);
    try {
      const items = group.items.filter((i) => picked.has(i.ticket_number))
        .map((i) => ({ ticket_ref: i.ticket_number, interaction_id: i.interaction_id }));
      const res = await api.bulkApprove(items);
      const failed = res.results.filter((r) => !r.ok);
      toast(`${res.approved} replies approved${failed.length ? ` · ${failed.length} skipped` : ""}`, failed.length ? "bad" : "good");
      setPicked(new Set());
      onDone();
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel icon={Repeat2} title={`${INTENT_TEXT[group.intent] ?? group.intent} · ${group.count} ${group.count === 1 ? "ticket" : "tickets"}`}
      subtitle="Read each draft, tick the ones you are happy with, then approve them together" bodyClass=""
      actions={
        <div className="actions">
          <button className="btn sm" onClick={() => setPicked(all ? new Set() : new Set(group.items.map((i) => i.ticket_number)))}>
            {all ? "Clear" : "Select all"}
          </button>
          <button className="btn primary sm" disabled={busy || picked.size === 0} onClick={approve}>
            <ShieldCheck size={14} /> {busy ? "Approving…" : `Approve ${picked.size || ""} selected`}
          </button>
        </div>
      }>
      <div className="bulk-list">
        {group.items.map((i) => (
          <label key={i.ticket_number} className="bulk-item" data-picked={picked.has(i.ticket_number)}>
            <input type="checkbox" checked={picked.has(i.ticket_number)} onChange={() => toggle(i.ticket_number)} />
            <div className="bulk-main">
              <div className="bulk-top">
                <b>{i.customer_name}</b>
                <span className="dim mono">{i.ticket_number}</span>
                {i.order_number && <span className="dim mono">{i.order_number}</span>}
                {i.repeat_count > 1 && <span className="pill amber">Asked {i.repeat_count}× about this order</span>}
                <span className="pill green" style={{ marginLeft: "auto" }}>Confidence {pct(i.confidence, 0)}</span>
              </div>
              <div className="muted bulk-msg">“{i.message}”</div>
              <div className="quote">{i.draft}</div>
              <Link className="bulk-edit" to={`/cx?t=${i.ticket_number}`}>Edit or escalate in the inbox →</Link>
            </div>
          </label>
        ))}
      </div>
    </Panel>
  );
}

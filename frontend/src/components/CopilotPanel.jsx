import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Ban, Bot, Check, CircleAlert, CircleCheck, Info, Pencil, Send, Sparkles, TriangleAlert, UserRound } from "lucide-react";
import { IntentPill, StatusPill } from "./ui.jsx";
import { pct } from "../useApi.js";

const STEPS = [
  ["Reading the message", "Haiku 4.5"],
  ["Finding the order", "code"],
  ["Checking rules and policy", "code"],
  ["Writing the reply", "Opus 5.5"],
  ["Checking the reply", "code + Haiku"],
];

// Animated progress while the analyze request is in flight. Advances on a timer and stops at the last step.
export function LoadingSteps() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 650);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="loading-steps" aria-live="polite">
      {STEPS.map(([name, who], i) => (
        <div key={name} className={`ls ${i < step ? "done" : i === step ? "now" : ""}`}>
          <span className="mk">{i < step && <Check size={12} strokeWidth={3} />}</span>
          {name}
          <span className="who">{who}</span>
        </div>
      ))}
    </div>
  );
}

const DECISION_TEXT = {
  APPROVED: "Approved and resolved",
  EDITED: "Edited, approved and resolved",
  REJECTED: "Draft rejected, ticket escalated",
  ESCALATED: "Escalated to a person",
};

/**
 * Shows one Copilot result and the agent's options.
 * props: result, onDecide(action, finalReply) | undefined (read-only), busy, segmentLink {to, label} | null
 */
export default function CopilotPanel({ result, onDecide, busy, segmentLink }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(result.draft ?? "");

  useEffect(() => {
    setEditing(false);
    setText(result.draft ?? "");
  }, [result.interaction_id, result.draft]);

  const c = result.classification;
  const decided = result.human_action;
  const canDecide = onDecide && !decided;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="cp-head">
        <StatusPill status={result.status} />
        <IntentPill intent={c.intent} />
        <span className="pill grey">Confidence {pct(c.confidence, 0)}</span>
        <span className="pill grey">{c.language}</span>
        {result.policy_used && <span className="pill violet">Policy: {result.policy_used}</span>}
        {result.fallback_mode && <span className="pill amber">Fallback mode</span>}
      </div>

      {decided && (
        <div className="callout green"><CircleCheck size={18} /><p><b>{DECISION_TEXT[decided] ?? decided}</b>{result.final_reply ? "Final reply saved below." : "No reply saved."}</p></div>
      )}

      {result.status === "NEEDS_HUMAN" && !decided && (
        <div className="callout red" role="alert">
          <TriangleAlert size={18} />
          <p><b>Copilot can't answer this one{result.escalation_tier ? ` · ${result.escalation_tier}` : ""}</b>{result.human_reason}</p>
        </div>
      )}
      {result.status === "NEEDS_INFO" && (
        <div className="callout amber"><Info size={18} /><p><b>Needs the order number</b>{result.human_reason} Copilot used the standard "ask for order number" reply.</p></div>
      )}
      {result.priority_note && (
        <div className="callout amber"><TriangleAlert size={18} /><p><b>Priority</b>{result.priority_note}</p></div>
      )}
      {segmentLink && (
        <div className="callout violet"><Sparkles size={18} /><p><b>This product is a flagged returns segment</b><Link to={segmentLink.to}>{segmentLink.label}</Link></p></div>
      )}

      {(result.draft || editing || result.final_reply) && (
        <div style={{ display: "grid", gap: 6 }}>
          <label htmlFor={`draft-${result.interaction_id}`} className="muted" style={{ fontSize: 12, fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
            {decided ? <><UserRound size={13} /> Final reply</> : editing ? <><Pencil size={13} /> Edit the reply</> : <><Bot size={13} /> Suggested reply</>}
          </label>
          {editing ? (
            <textarea id={`draft-${result.interaction_id}`} className="draft-box" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          ) : (
            <div id={`draft-${result.interaction_id}`} className="draft-box">{decided ? result.final_reply ?? result.draft : result.draft}</div>
          )}
        </div>
      )}

      {result.check && !decided && (
        <div className="checks">
          {result.check.passed
            ? <div><CircleCheck size={15} color="var(--green)" /> Passed the automatic check: facts, order number, amounts and dates match the order.</div>
            : result.check.issues.map((issue) => <div key={issue}><CircleAlert size={15} color="var(--amber)" /> {issue}</div>)}
        </div>
      )}

      {result.notes?.length > 0 && (
        <div className="run-meta">{result.notes.map((n) => <span key={n}>ⓘ {n}</span>)}</div>
      )}

      {canDecide && (
        <div className="actions">
          {editing ? (
            <>
              <button className="btn primary" disabled={busy || !text.trim()} onClick={() => onDecide("EDITED", text)}><Send size={14} /> Save and send</button>
              <button className="btn" disabled={busy} onClick={() => { setEditing(false); setText(result.draft ?? ""); }}>Cancel</button>
            </>
          ) : result.status === "NEEDS_HUMAN" ? (
            <>
              <button className="btn primary" disabled={busy} onClick={() => onDecide("ESCALATED")}><UserRound size={14} /> Assign to {result.escalation_tier ?? "a person"}</button>
              <button className="btn" disabled={busy} onClick={() => setEditing(true)}><Pencil size={14} /> Reply manually</button>
            </>
          ) : (
            <>
              <button className="btn good" disabled={busy || !result.draft} onClick={() => onDecide("APPROVED")}><Check size={14} /> Approve and send</button>
              <button className="btn" disabled={busy} onClick={() => setEditing(true)}><Pencil size={14} /> Edit</button>
              {result.status === "DRAFTED" && <button className="btn danger" disabled={busy} onClick={() => onDecide("REJECTED")}><Ban size={14} /> Reject</button>}
            </>
          )}
        </div>
      )}

      <div className="run-meta">
        <span>Attempts: {result.attempts ?? "–"}</span>
        {result.latency_ms != null && <span>Time: {(result.latency_ms / 1000).toFixed(1)} s</span>}
        {result.cost_usd != null && <span>Cost: ${result.cost_usd.toFixed(4)}</span>}
        {result.interaction_id && <span className="mono">Run {result.interaction_id.slice(0, 8)}</span>}
      </div>
    </div>
  );
}

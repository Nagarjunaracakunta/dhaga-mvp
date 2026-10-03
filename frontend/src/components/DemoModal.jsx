import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CircleAlert, CircleCheck, LoaderCircle, Play, Zap } from "lucide-react";
import { api } from "../api.js";
import { CloseButton, IntentPill, Overlay, StatusPill } from "./ui.jsx";

const MAX_TICKETS = 5;

// Runs Copilot on the first few open tickets, one after another, and shows each result as it lands.
export default function DemoModal({ onClose }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [phase, setPhase] = useState("ready"); // ready | running | done | error
  const [error, setError] = useState(null);
  const cancelled = useRef(false);

  useEffect(() => () => { cancelled.current = true; }, []);

  async function run() {
    setPhase("running");
    setError(null);
    try {
      const open = await api.tickets({ status: "OPEN", limit: MAX_TICKETS });
      if (!open.length) {
        setPhase("done");
        return;
      }
      setRows(open.map((t) => ({ ticket: t, state: "waiting" })));
      for (let i = 0; i < open.length; i++) {
        if (cancelled.current) return;
        setRows((r) => r.map((x, j) => (j === i ? { ...x, state: "running" } : x)));
        try {
          const result = await api.analyze(open[i].ticket_number);
          setRows((r) => r.map((x, j) => (j === i ? { ...x, state: "done", result } : x)));
        } catch (e) {
          setRows((r) => r.map((x, j) => (j === i ? { ...x, state: "failed", error: e.message } : x)));
        }
      }
      setPhase("done");
    } catch (e) {
      setError(e);
      setPhase("error");
    }
  }

  const drafted = rows.filter((r) => r.result?.status === "DRAFTED").length;
  const human = rows.filter((r) => r.result && r.result.status !== "DRAFTED").length;

  return (
    <Overlay kind="modal" onClose={onClose} labelledBy="demo-title">
      <div className="dhead">
        <div>
          <h2 id="demo-title" style={{ display: "flex", gap: 8, alignItems: "center" }}><Zap size={18} color="var(--pink)" /> 1-Click Copilot Demo</h2>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            Runs Copilot on up to {MAX_TICKETS} open tickets: classify, find the order, apply rules, draft and check. Every result waits in the inbox for an agent.
          </p>
        </div>
        <CloseButton onClick={onClose} />
      </div>

      {phase === "ready" && (
        <button className="btn hot" onClick={run} style={{ justifySelf: "start" }}><Play size={15} /> Start demo</button>
      )}

      {phase === "error" && <div className="callout red"><CircleAlert size={18} /><p>{error.message}</p></div>}

      {rows.length > 0 && (
        <div style={{ display: "grid", gap: 8 }}>
          {rows.map(({ ticket, state, result, error: err }) => (
            <div className="demo-row" key={ticket.ticket_id}>
              {state === "running" ? <LoaderCircle size={18} className="spin" style={{ animation: "spin .8s linear infinite", color: "var(--violet)" }} />
                : state === "done" ? <CircleCheck size={18} color="var(--green)" />
                : state === "failed" ? <CircleAlert size={18} color="var(--red)" />
                : <span className="dim">•</span>}
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}><span className="mono dim">{ticket.ticket_number}</span> {ticket.customer_name}</div>
                <div className="muted" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {err ?? result?.human_reason ?? result?.draft?.split("\n")[0] ?? ticket.message}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {result && <IntentPill intent={result.classification.intent} />}
                {result && <StatusPill status={result.status} />}
              </div>
            </div>
          ))}
        </div>
      )}

      {phase === "done" && (
        <>
          {rows.length === 0
            ? <div className="callout amber"><CircleAlert size={18} /><p>No open tickets left. Restart the backend to reset the demo data.</p></div>
            : <div className="callout green"><CircleCheck size={18} /><p><b>{drafted} drafts ready, {human} need a person.</b>Open the inbox to review, edit and approve them.</p></div>}
          <div className="actions">
            <button className="btn primary" onClick={() => { onClose(); navigate("/cx"); }}>Open CX Inbox</button>
            <button className="btn" onClick={() => { onClose(); navigate("/cx/metrics"); }}>See metrics</button>
          </div>
        </>
      )}
    </Overlay>
  );
}

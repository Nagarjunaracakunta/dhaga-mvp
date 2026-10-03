// Small shared building blocks used by every page.
import { CircleAlert, Inbox, RefreshCw, X } from "lucide-react";
import { useEffect } from "react";
import { label } from "../useApi.js";

export function Panel({ icon: Icon, title, subtitle, actions, children, className = "", bodyClass = "panel-body" }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div className="panel-title">
            {Icon && <span className="ico"><Icon size={16} /></span>}
            <div>
              <h2>{title}</h2>
              {subtitle && <p>{subtitle}</p>}
            </div>
          </div>
          {actions}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Stat({ label: k, value, sub, icon: Icon, tone = "violet", loading }) {
  return (
    <div className={`panel stat tone-${tone}`}>
      <div className="top">
        <span className="k">{k}</span>
        {Icon && <span className="ico"><Icon size={15} /></span>}
      </div>
      {loading ? <div className="skeleton" style={{ height: 34, width: "60%" }} /> : <div className="v">{value}</div>}
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

const STATUS_TONE = {
  OPEN: "grey", DRAFTED: "violet", RESOLVED: "green", ESCALATED: "red",
  NEEDS_HUMAN: "red", NEEDS_INFO: "amber",
};
const STATUS_TEXT = { DRAFTED: "Draft ready", NEEDS_HUMAN: "Needs a person", NEEDS_INFO: "Needs info" };

export function StatusPill({ status }) {
  if (!status) return null;
  return <span className={`pill ${STATUS_TONE[status] ?? "grey"}`}>{STATUS_TEXT[status] ?? label(status)}</span>;
}

export const INTENT_TEXT = {
  WISMO: "Where is my order",
  DELIVERED_NOT_RECEIVED: "Delivered, not received",
  CANCEL_ORDER: "Cancel order",
  RETURN_REFUND: "Return / refund",
  COD_PAYMENT: "COD payment",
  OTHER: "Unclear",
};

export function IntentPill({ intent }) {
  if (!intent) return null;
  return <span className="pill grey">{INTENT_TEXT[intent] ?? intent}</span>;
}

export function Empty({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="empty">
      <Icon size={28} />
      <b style={{ color: "var(--text)" }}>{title}</b>
      {children && <div>{children}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="callout red" role="alert">
      <CircleAlert size={18} />
      <div style={{ flex: 1 }}>
        <b>Couldn't load this</b>
        <p>{error?.message ?? "Unknown error"}</p>
      </div>
      {onRetry && <button className="btn sm" onClick={onRetry}><RefreshCw size={13} /> Retry</button>}
    </div>
  );
}

export function Skeleton({ rows = 3, height = 18 }) {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height }} />)}
    </div>
  );
}

export function HBars({ rows, max, format = (v) => v, tone }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="hbars">
      {rows.map((r) => (
        <div className="hbar" key={r.label} title={`${r.label}: ${format(r.value)}`}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}</span>
          <div className="track"><div className={`fill ${r.tone ?? tone ?? ""}`} style={{ width: `${(r.value / top) * 100}%` }} /></div>
          <span className="v">{format(r.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function Overlay({ onClose, children, kind = "drawer", labelledBy }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className={kind} role="dialog" aria-modal="true" aria-labelledby={labelledBy}>{children}</div>
    </>
  );
}

export function CloseButton({ onClick }) {
  return <button className="btn ghost" onClick={onClick} aria-label="Close"><X size={18} /></button>;
}

export function ChartTip({ active, payload, label: l, render }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tip">{render ? render(payload[0].payload) : <><b>{l}</b>{payload[0].value}</>}</div>;
}

import { useMemo, useState } from "react";
import { CircleCheck, Filter, Search, ShieldCheck } from "lucide-react";
import { api } from "../api.js";
import { label, num, useApi } from "../useApi.js";
import { Empty, ErrorBox, HBars, Panel, Skeleton, Stat } from "../components/ui.jsx";

const EXPLAIN = {
  duplicate_order_id: "Same order ID appears twice; the first copy is kept",
  duplicate_return_id: "Same return ID appears twice; the first copy is kept",
  invalid_order_date: "Date is not YYYY-MM-DD",
  invalid_return_date: "Date is not YYYY-MM-DD",
  missing_product_id: "Product ID is blank",
  order_not_found: "Return points to an order that doesn't exist or was rejected",
  product_mismatch_with_order: "Return's product differs from the product on its order",
  unknown_product_id: "Product isn't in the catalogue",
  unknown_return_reason: "Reason is neither a dropdown value nor Other",
  unknown_size: "Size text can't be mapped to a standard size",
};

export default function DataQuality() {
  const rejected = useApi(() => api.returnsRejected(), []);
  const summary = useApi(() => api.returnsSummary(), []);
  const [reason, setReason] = useState("");
  const [query, setQuery] = useState("");

  const byReason = useMemo(() => {
    const c = {};
    (rejected.data ?? []).forEach((r) => { c[r.reason] = (c[r.reason] ?? 0) + 1; });
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  }, [rejected.data]);

  const rows = (rejected.data ?? []).filter((r) =>
    (!reason || r.reason === reason) && (!query || r.record_id.toLowerCase().includes(query.toLowerCase())));
  const s = summary.data;

  return (
    <div className="grid">
      <div className="grid stats">
        <Stat label="Raw orders" value={num(s?.raw_orders)} sub={`${num(s?.total_orders)} kept after cleaning`} icon={ShieldCheck} loading={summary.loading} />
        <Stat label="Raw returns" value={num(s?.raw_returns)} sub={`${num(s?.total_returns)} kept after cleaning`} icon={ShieldCheck} tone="cyan" loading={summary.loading} />
        <Stat label="Rejected rows" value={num(s?.rejected_records)} sub="Each with exactly one reason" icon={Filter} tone="amber" loading={summary.loading} />
      </div>

      <div className="grid two">
        <Panel icon={Filter} title="Why rows were rejected" subtitle="Click a reason to filter the table">
          {rejected.loading ? <Skeleton rows={6} />
            : rejected.error ? <ErrorBox error={rejected.error} onRetry={rejected.reload} />
            : byReason.length === 0 ? <Empty icon={CircleCheck} title="Nothing rejected">Every row passed validation.</Empty>
            : (
              <div style={{ display: "grid", gap: 6 }}>
                {byReason.map(([k, v]) => (
                  <button key={k} className="rowlink" onClick={() => setReason(reason === k ? "" : k)}
                    style={{ background: reason === k ? "var(--violet-soft)" : undefined, borderRadius: 8, padding: "10px 10px" }}>
                    <span className="main">{label(k)}</span>
                    <span className="side"><b>{v}</b></span>
                    <span className="sub">{EXPLAIN[k] ?? k}</span>
                  </button>
                ))}
              </div>
            )}
        </Panel>

        <Panel icon={Search} title="Rejected rows" subtitle={reason ? `Filtered: ${label(reason)}` : "All reasons"} bodyClass=""
          actions={reason && <button className="btn sm" onClick={() => setReason("")}>Clear filter</button>}>
          <div className="panel-body" style={{ paddingBottom: 0 }}>
            <label className="search">
              <Search size={15} className="dim" />
              <input id="rejected-search" placeholder="Search record ID" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
          </div>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="t">
              <thead><tr><th>Source</th><th>Record</th><th>Reason</th></tr></thead>
              <tbody>
                {rows.map((r, n) => (
                  <tr key={n}><td className="muted">{r.source}</td><td className="mono">{r.record_id || "(blank)"}</td><td>{label(r.reason)}</td></tr>
                ))}
                {rows.length === 0 && !rejected.loading && <tr><td colSpan={3} className="muted">No rows match.</td></tr>}
              </tbody>
            </table>
          </div>
          {byReason.length > 0 && <div className="panel-body"><HBars rows={byReason.map(([k, v]) => ({ label: label(k), value: v }))} /></div>}
        </Panel>
      </div>
    </div>
  );
}

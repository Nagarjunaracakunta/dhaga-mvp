import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownUp, Bot, Layers, MessageSquareText, Package, PackageX, RotateCcw, Scale, TriangleAlert } from "lucide-react";
import { api } from "../api.js";
import { label, num, pct, useApi } from "../useApi.js";
import { ChartTip, CloseButton, ErrorBox, HBars, Overlay, Panel, Skeleton, Stat } from "../components/ui.jsx";

const DIMENSIONS = [["size", "Size"], ["colour", "Colour"], ["category", "Category"], ["product_id", "Product"]];

export default function Returns() {
  const [params, setParams] = useSearchParams();
  const segmentId = params.get("segment");
  const [by, setBy] = useState("size");

  const summary = useApi(() => api.returnsSummary(), []);
  const insights = useApi(() => api.returnsInsights(), []);
  const reasons = useApi(() => api.returnsReasons(), []);
  const breakdown = useApi(() => api.returnsBreakdown(by), [by]);
  const products = useApi(() => api.returnsProducts(), []);

  const s = summary.data;
  const baseline = s?.return_rate ?? 0;
  const segment = insights.data?.find((i) => i.insight_id === segmentId);

  const reasonRows = useMemo(() => {
    const totals = {};
    (reasons.data ?? []).forEach((r) => { totals[r.primary_reason] = (totals[r.primary_reason] ?? 0) + r.count; });
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
      label: k === "UNCLASSIFIED" ? "Unclassified (Other)" : k === "UNSPECIFIED" ? "No reason given" : label(k),
      value: v, tone: k === "UNCLASSIFIED" || k === "UNSPECIFIED" ? "muted" : "",
    }));
  }, [reasons.data]);

  const chartRows = useMemo(() => {
    const names = Object.fromEntries((products.data ?? []).map((p) => [p.product_id, p.product_name]));
    return (breakdown.data ?? []).map((r) => ({ ...r, name: by === "product_id" ? names[r.product_id] ?? r.product_id : r[by] }));
  }, [breakdown.data, products.data, by]);

  return (
    <div className="grid">
      <div className="grid stats">
        <Stat label="Return rate" value={pct(s?.return_rate)} sub={s ? `${num(s.total_returns)} returns · ${num(s.total_orders)} orders` : ""} icon={RotateCcw} tone="red" loading={summary.loading} />
        <Stat label='Marked "Other"' value={pct(s?.other_share, 0)} sub="Dropdown gives no real reason" icon={MessageSquareText} tone="amber" loading={summary.loading} />
        <Stat label="Waiting for AI" value={num(s?.other_with_comment)} sub={`${num(s?.other_without_comment)} more have no comment at all`} icon={Bot} tone="pink" loading={summary.loading} />
        <Stat label="Flagged segments" value={num(insights.data?.length)} sub="≥1.5× the shop average, ≥15 returns" icon={TriangleAlert} tone="violet" loading={insights.loading} />
      </div>

      <Panel icon={TriangleAlert} title="Flagged segments" subtitle="Click a card to see the reason mix and what customers wrote">
        {insights.loading ? <Skeleton rows={2} height={90} />
          : insights.error ? <ErrorBox error={insights.error} onRetry={insights.reload} />
          : (
            <div className="grid three">
              {insights.data.map((i) => (
                <button key={i.insight_id} className="seg-card" onClick={() => setParams({ segment: i.insight_id })}>
                  <div className="row">
                    <span className="t">{i.product_name}</span>
                    <span className="lift">{i.lift}×</span>
                  </div>
                  <div className="row muted" style={{ fontSize: 12.5 }}>
                    <span>{Object.entries(i.segment).map(([k, v]) => `${label(k)} ${v}`).join(", ") || "Whole product"}</span>
                    <span>{i.returns}/{i.orders} returned</span>
                  </div>
                  <HBars rows={[{ label: "This segment", value: i.return_rate, tone: "pink" }, { label: "Shop average", value: i.baseline_rate, tone: "muted" }]}
                    max={Math.max(i.return_rate, i.baseline_rate) * 1.1} format={(v) => pct(v)} />
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className="pill grey">{pct(i.unclassified_share, 0)} unclassified</span>
                    <span className="pill violet">{label(i.dimension)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
      </Panel>

      <div className="grid two">
        <Panel icon={Scale} title="Return rate by…" subtitle="Dashed line is the shop average"
          actions={
            <div className="seg-toggle" role="group" aria-label="Group by">
              {DIMENSIONS.map(([k, l]) => <button key={k} aria-pressed={by === k} onClick={() => setBy(k)}>{l}</button>)}
            </div>
          }>
          {breakdown.loading ? <Skeleton rows={5} height={30} />
            : breakdown.error ? <ErrorBox error={breakdown.error} onRetry={breakdown.reload} />
            : (
              <div style={{ height: 290 }}>
                <ResponsiveContainer>
                  <BarChart data={chartRows} margin={{ top: 10, right: 10, bottom: by === "product_id" || by === "category" ? 50 : 10 }}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="name" interval={0} angle={by === "product_id" || by === "category" ? -30 : 0} textAnchor={by === "product_id" || by === "category" ? "end" : "middle"} height={by === "product_id" || by === "category" ? 60 : 30} />
                    <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} width={42} />
                    <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} content={<ChartTip render={(p) => <><b>{p.name}</b>{pct(p.return_rate)} returned · {num(p.returns)} of {num(p.orders)}</>} />} />
                    <ReferenceLine y={baseline} stroke="#f5b84a" strokeDasharray="5 4" />
                    <Bar dataKey="return_rate" isAnimationActive={false} radius={[6, 6, 0, 0]} maxBarSize={46}>
                      {chartRows.map((r) => <Cell key={r.name} fill={r.return_rate >= baseline * 1.5 ? "#e8509a" : "#8b7cf8"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
        </Panel>

        <Panel icon={Layers} title="Why products come back" subtitle="Grey bars have no usable reason yet">
          {reasons.loading ? <Skeleton rows={6} />
            : reasons.error ? <ErrorBox error={reasons.error} onRetry={reasons.reload} />
            : <HBars rows={reasonRows} />}
          <p className="muted" style={{ margin: "14px 0 0", fontSize: 12.5 }}>
            Stage 2 will have Claude read the "Other" comments and move most of the top bar into real reasons.
          </p>
        </Panel>
      </div>

      <ProductTable products={products} />

      {segment && <SegmentDrawer segment={segment} onClose={() => setParams({})} />}
    </div>
  );
}

function ProductTable({ products }) {
  const [sort, setSort] = useState({ key: "return_rate", dir: -1 });
  const rows = useMemo(() => [...(products.data ?? [])].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key];
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir;
  }), [products.data, sort]);
  const reasonCols = Object.keys(products.data?.[0] ?? {}).filter((k) => k.startsWith("n_") && k !== "n_UNSPECIFIED");
  const head = (key, text, numeric) => (
    <th className={numeric ? "num" : ""}>
      <button onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : -1 }))}>
        {text} {sort.key === key && <ArrowDownUp size={11} />}
      </button>
    </th>
  );
  return (
    <Panel icon={Package} title="Products" subtitle="Click a column to sort" bodyClass="">
      {products.loading ? <div className="panel-body"><Skeleton rows={6} /></div>
        : products.error ? <div className="panel-body"><ErrorBox error={products.error} onRetry={products.reload} /></div>
        : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="t">
              <thead><tr>
                {head("product_name", "Product")}{head("category", "Category")}
                {head("orders", "Orders", true)}{head("returns", "Returns", true)}{head("return_rate", "Rate", true)}
                {reasonCols.map((k) => head(k, label(k.slice(2)), true))}
              </tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.product_id}>
                    <td><b>{p.product_name}</b> <span className="dim mono">{p.product_id}</span></td>
                    <td className="muted">{p.category}</td>
                    <td className="num">{num(p.orders)}</td>
                    <td className="num">{num(p.returns)}</td>
                    <td className="num" style={{ color: p.return_rate >= 0.15 ? "var(--pink)" : undefined, fontWeight: 700 }}>{pct(p.return_rate)}</td>
                    {reasonCols.map((k) => <td key={k} className="num muted">{num(p[k])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </Panel>
  );
}

function SegmentDrawer({ segment: i, onClose }) {
  const mix = Object.entries(i.reason_breakdown).map(([k, v]) => ({
    label: k === "UNCLASSIFIED" ? "Unclassified" : label(k), value: v, tone: k === "UNCLASSIFIED" ? "muted" : "",
  }));
  const seg = Object.entries(i.segment).map(([k, v]) => `${label(k)} ${v}`).join(", ") || "Whole product";
  return (
    <Overlay onClose={onClose} labelledBy="seg-title">
      <div className="dhead">
        <div>
          <span className="pill pink">{i.lift}× the shop average</span>
          <h2 id="seg-title" style={{ marginTop: 8 }}>{i.product_name} · {seg}</h2>
          <p className="muted" style={{ margin: "4px 0 0" }}>{i.returns} of {i.orders} orders returned ({pct(i.return_rate)}) against a shop average of {pct(i.baseline_rate)}.</p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <Panel icon={Layers} title="Known reasons">
        <HBars rows={mix} />
      </Panel>
      <Panel icon={MessageSquareText} title="What customers wrote" subtitle='Sample "Other" comments for this segment'>
        <div style={{ display: "grid", gap: 8 }}>
          {i.sample_comments.length
            ? i.sample_comments.map((c, n) => <div className="quote" key={n}>“{c}”</div>)
            : <span className="muted">No comments for this segment.</span>}
        </div>
      </Panel>
      <div className="callout violet">
        <PackageX size={18} />
        <p><b>{pct(i.unclassified_share, 0)} of these returns have no real reason yet</b>
          AI classification of "Other" comments arrives in stage 2. It will turn comments like these into categories such as Fit → Too tight → Shoulders.</p>
      </div>
      <button className="btn" disabled title="Coming in stage 2"><Bot size={15} /> Classify comments with AI</button>
    </Overlay>
  );
}

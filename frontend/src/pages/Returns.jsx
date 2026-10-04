import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownUp, Bot, Check, Layers, LoaderCircle, MessageSquareText, Package, PackageX, RotateCcw, Scale, Sparkles, TriangleAlert, UserRound } from "lucide-react";
import { api } from "../api.js";
import { label, num, pct, useApi } from "../useApi.js";
import { ChartTip, CloseButton, Empty, ErrorBox, HBars, Overlay, Panel, Skeleton, Stat, PageHeader } from "../components/ui.jsx";
import { useToast } from "../components/Toast.jsx";
import { CHART } from "../theme.js";

const DIMENSIONS = [["size", "Size"], ["colour", "Colour"], ["category", "Category"], ["product_id", "Product"]];

const CATEGORIES = ["FIT", "COLOUR", "QUALITY", "DAMAGE", "WRONG_ITEM", "CHANGED_MIND", "UNCLEAR"];
const reasonText = (k) => ({ UNCLASSIFIED: "Unclassified (Other)", UNSPECIFIED: "No reason given", WRONG_ITEM: "Wrong item",
  CHANGED_MIND: "Changed mind" }[k] ?? label(k));
const detailText = (sub) => (sub ? sub.split(":").map(label).join(" · ") : "");

export default function Returns() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const segmentId = params.get("segment");
  const [by, setBy] = useState("size");

  const summary = useApi(() => api.returnsSummary(), []);
  const insights = useApi(() => api.returnsInsights(), []);
  const reasons = useApi(() => api.returnsReasons(), []);
  const breakdown = useApi(() => api.returnsBreakdown(by), [by]);
  const products = useApi(() => api.returnsProducts(), []);
  const queue = useApi(() => api.returnsReviewQueue(), []);
  const briefs = useApi(() => api.returnsBriefs(), []);
  const refreshAll = () => [summary, insights, reasons, breakdown, products, queue, briefs].forEach((x) => x.reload());

  const s = summary.data;
  const baseline = s?.return_rate ?? 0;
  const segment = insights.data?.find((i) => i.insight_id === segmentId);
  const minReturns = s?.data_source === "supabase" ? 8 : 15;

  const reasonRows = useMemo(() => {
    const totals = {};
    (reasons.data ?? []).forEach((r) => { totals[r.primary_reason] = (totals[r.primary_reason] ?? 0) + r.count; });
    return Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
      label: reasonText(k), value: v, tone: ["UNCLASSIFIED", "UNSPECIFIED", "UNCLEAR"].includes(k) ? "muted" : "",
    }));
  }, [reasons.data]);

  const chartRows = useMemo(() => {
    const names = Object.fromEntries((products.data ?? []).map((p) => [p.product_id, p.sku ?? p.product_name]));
    return (breakdown.data ?? []).map((r) => ({ ...r, name: by === "product_id" ? names[r.product_id] ?? r.product_id : r[by] }));
  }, [breakdown.data, products.data, by]);

  const explained = s ? s.ai_classified + s.human_reviewed : 0;

  return (
    <div className="grid">
      <PageHeader title="Return insights" subtitle={'Which products, sizes and colours come back too often, and why. "Other" comments are explained by AI and checked by people.'} />
      <div className="grid stats">
        <Stat label="Return rate" value={pct(s?.return_rate)} sub={s ? `${num(s.total_returns)} returns · ${num(s.total_orders)} orders` : ""} icon={RotateCcw} tone="red" loading={summary.loading} />
        <Stat label='Marked "Other"' value={pct(s?.other_share, 0)} sub="The dropdown gives no real reason" icon={MessageSquareText} tone="amber" loading={summary.loading} />
        <Stat label='"Other" explained' value={s ? `${num(explained)} / ${num(s.other_with_comment)}` : "–"} sub={s ? `${num(s.other_pending)} still waiting for AI` : ""} icon={Bot} tone="green" loading={summary.loading} />
        <Stat label="Needs a person" value={num(s?.needs_review)} sub={s ? `${num(s.human_reviewed)} already reviewed` : ""} icon={UserRound} tone="pink" loading={summary.loading} />
        <Stat label="Flagged segments" value={num(insights.data?.length)} sub={`≥1.5× the shop average, ≥${minReturns} returns`} icon={TriangleAlert} tone="violet" loading={insights.loading} />
      </div>

      <ClassifyPanel s={s} queue={queue} onChanged={refreshAll} toast={toast} />

      <BriefsPanel briefs={briefs} onChanged={refreshAll} toast={toast} />

      <Panel icon={TriangleAlert} title="Flagged segments" subtitle="Click a card to see the reason mix and what customers wrote">
        {insights.loading ? <Skeleton rows={2} height={90} />
          : insights.error ? <ErrorBox error={insights.error} onRetry={insights.reload} />
          : insights.data.length === 0 ? <Empty title="Nothing flagged">No product, size or colour is returned unusually often.</Empty>
          : (
            <div className="grid three">
              {insights.data.map((i) => (
                <button key={i.insight_id} className="seg-card" onClick={() => setParams({ segment: i.insight_id })}>
                  <div className="row">
                    <span className="t">{i.product_name}</span>
                    <span className="lift">{i.lift}×</span>
                  </div>
                  <div className="row muted" style={{ fontSize: 12.5 }}>
                    <span>{Object.entries(i.segment).map(([k, v]) => `${label(k)} ${v}`).join(", ") || "Whole product"}{i.sku ? ` · ${i.sku}` : ""}</span>
                    <span>{i.returns}/{i.orders} returned</span>
                  </div>
                  <HBars rows={[{ label: "This segment", value: i.return_rate, tone: "pink" }, { label: "Shop average", value: i.baseline_rate, tone: "muted" }]}
                    max={Math.max(i.return_rate, i.baseline_rate) * 1.1} format={(v) => pct(v)} />
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {topReason(i) && <span className="pill violet">Mostly {reasonText(topReason(i)).toLowerCase()}</span>}
                    <span className="pill grey">{pct(i.unclassified_share, 0)} unclassified</span>
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
                    <XAxis dataKey="name" interval={by === "product_id" ? "preserveStartEnd" : 0} angle={by === "product_id" || by === "category" ? -30 : 0} textAnchor={by === "product_id" || by === "category" ? "end" : "middle"} height={by === "product_id" || by === "category" ? 60 : 30} />
                    <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} width={42} />
                    <Tooltip cursor={{ fill: CHART.cursor }} content={<ChartTip render={(p) => <><b>{p.name}</b>{pct(p.return_rate)} returned · {num(p.returns)} of {num(p.orders)}</>} />} />
                    <ReferenceLine y={baseline} stroke={CHART.accent} strokeDasharray="5 4" />
                    <Bar dataKey="return_rate" isAnimationActive={false} radius={[6, 6, 0, 0]} maxBarSize={46}>
                      {chartRows.map((r) => <Cell key={r.name} fill={r.return_rate >= baseline * 1.5 ? CHART.accent : CHART.primary} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
        </Panel>

        <Panel icon={Layers} title="Why products come back" subtitle="Grey bars have no usable reason">
          {reasons.loading ? <Skeleton rows={6} />
            : reasons.error ? <ErrorBox error={reasons.error} onRetry={reasons.reload} />
            : <HBars rows={reasonRows} />}
          <p className="muted" style={{ margin: "14px 0 0", fontSize: 12.5 }}>
            {s?.other_pending ? `${num(s.other_pending)} "Other" comments are still unclassified. Classify them above to turn the top bar into real reasons.`
              : `Every "Other" comment now has a reason, from AI or a person. Fit, colour and quality are what listing fixes can prevent.`}
          </p>
        </Panel>
      </div>

      <ProductTable products={products} />

      {segment && <SegmentDrawer segment={segment} onClose={() => setParams({})} onChanged={refreshAll} toast={toast} />}
    </div>
  );
}

function topReason(i) {
  const known = Object.entries(i.reason_breakdown).filter(([k]) => !["UNCLASSIFIED", "UNSPECIFIED", "UNCLEAR"].includes(k));
  return known.sort((a, b) => b[1] - a[1])[0]?.[0];
}

function ReviewControls({ returnId, aiCategory, onChanged, toast }) {
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState(aiCategory ?? "FIT");
  async function send(category) {
    setBusy(true);
    try {
      const r = await api.returnsReview(returnId, category);
      toast(r.action === "accepted" ? "Reason accepted" : `Corrected to ${reasonText(category)}`);
      onChanged();
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      {aiCategory && <button className="btn sm good" disabled={busy} onClick={() => send(aiCategory)}><Check size={13} /> Accept</button>}
      <select className="select" style={{ padding: "4px 8px", fontSize: 12 }} value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Correct reason">
        {CATEGORIES.map((c) => <option key={c} value={c}>{reasonText(c)}</option>)}
      </select>
      <button className="btn sm" disabled={busy || pick === aiCategory} onClick={() => send(pick)}>Correct</button>
    </div>
  );
}

function ClassifyPanel({ s, queue, onChanged, toast }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const pending = s?.other_pending ?? 0;

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.returnsClassify({ limit: 300 });
      toast(r.classified ? `${r.classified} comments classified for $${r.cost_usd.toFixed(3)} · ${r.needs_review} need a person` : r.message);
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }

  return (
    <Panel icon={Bot} title='Explain the "Other" returns'
      subtitle="Claude Haiku reads each comment (many at once) and picks a real reason. Unsure or vague ones go to a person."
      actions={<button className="btn hot" disabled={!s || running || pending === 0} onClick={run}>
        <Sparkles size={15} /> {running ? "Classifying…" : pending ? `Classify ${num(pending)} comments with AI` : "All comments classified"}
      </button>}>
      <div style={{ display: "grid", gap: 14 }}>
        {running && (
          <div className="callout violet"><LoaderCircle size={18} style={{ animation: "spin .8s linear infinite" }} />
            <p><b>Reading {num(pending)} comments in parallel</b>This takes about a minute and costs about ${(pending * 0.00105).toFixed(2)}.</p></div>
        )}
        {error && <ErrorBox error={error} onRetry={run} />}
        <div className="muted" style={{ fontSize: 12.5, fontWeight: 600 }}>Waiting for a person ({num(queue.data?.length ?? 0)})</div>
        {queue.loading ? <Skeleton rows={3} height={40} />
          : queue.error ? <ErrorBox error={queue.error} onRetry={queue.reload} />
          : queue.data.length === 0 ? <p className="muted" style={{ margin: 0 }}>Nothing to review. Low-confidence or vague AI reasons appear here.</p>
          : (
            <div className="table-wrap">
              <table className="t">
                <thead><tr><th>Customer wrote</th><th>Product</th><th>AI reason</th><th className="num">Confidence</th><th>Your call</th></tr></thead>
                <tbody>
                  {queue.data.slice(0, 12).map((q) => (
                    <tr key={q.return_id}>
                      <td>“{q.return_comment}”</td>
                      <td className="muted">{q.product_name} · {q.size}</td>
                      <td><span className="pill amber">{reasonText(q.ai_category)}</span> <span className="muted" style={{ fontSize: 12 }}>{detailText(q.ai_subcategory)}</span></td>
                      <td className="num">{pct(q.ai_confidence, 0)}</td>
                      <td><ReviewControls returnId={q.return_id} aiCategory={q.ai_category} onChanged={onChanged} toast={toast} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>
    </Panel>
  );
}

const BRIEF_SEVERITY = (lift) => (lift >= 2 ? ["High", "pink"] : lift >= 1.6 ? ["Medium", "amber"] : ["Low", "grey"]);
const BRIEF_REVIEW = [["approved", "Approve"], ["needs_followup", "Follow up"], ["dismissed", "Dismiss"]];

function BriefsPanel({ briefs, onChanged, toast }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  async function generate() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.returnsGenerateBriefs({ topK: 5 });
      toast(r.generated ? `${r.generated} brief(s) written for $${(r.cost_usd ?? 0).toFixed(3)} · ${r.needs_manual_review ?? 0} need a manual read` : r.message);
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }

  const rows = briefs.data ?? [];
  return (
    <Panel icon={Sparkles} title="Investigation briefs"
      subtitle="Claude Sonnet writes a short brief for each flagged segment; a second model fact-checks it before you see it."
      actions={<button className="btn hot" disabled={running} onClick={generate}>
        <Sparkles size={15} /> {running ? "Writing…" : "Generate briefs for the top segments"}
      </button>}>
      <div style={{ display: "grid", gap: 12 }}>
        {error && <ErrorBox error={error} onRetry={generate} />}
        {briefs.loading ? <Skeleton rows={2} height={90} />
          : briefs.error ? <ErrorBox error={briefs.error} onRetry={briefs.reload} />
          : rows.length === 0 ? <p className="muted" style={{ margin: 0 }}>No briefs yet. Click "Generate briefs" to write one for each flagged segment.</p>
          : rows.map((b) => {
            const lift = b.evidence?.lift ?? 0;
            const [sev, tone] = BRIEF_SEVERITY(lift);
            return (
              <div className="quote" key={b.insight_id} style={{ display: "grid", gap: 8 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span className={`pill ${tone}`}>{sev}</span>
                  <b>{b.brief?.headline || b.product_name}</b>
                  {b.stale && <span className="pill grey">stale</span>}
                </div>
                {b.status === "needs_manual_review" && (
                  <div className="callout amber"><TriangleAlert size={18} />
                    <p><b>Did not pass the automated fact check — read the numbers yourself</b>{(b.open_issues || []).join("; ")}</p></div>
                )}
                {b.brief?.explanation && <span>{b.brief.explanation}</span>}
                {b.brief?.suggested_action && <span className="muted"><b>Suggested next step:</b> {b.brief.suggested_action}</span>}
                {b.evidence && (
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    {pct(b.evidence.return_rate_pct / 100)} returned · {b.evidence.lift}× average · {num(b.evidence.returns)}/{num(b.evidence.orders)} orders
                  </span>
                )}
                <BriefReview insightId={b.insight_id} current={b.review_status} onChanged={onChanged} toast={toast} />
              </div>
            );
          })}
      </div>
    </Panel>
  );
}

function BriefReview({ insightId, current, onChanged, toast }) {
  const [status, setStatus] = useState(current && current !== "pending" ? current : "approved");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api.returnsBriefReview(insightId, status, note);
      toast(`Saved: ${status.replace("_", " ")}`);
      onChanged();
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      <select className="select" style={{ padding: "4px 8px", fontSize: 12 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Your decision">
        {BRIEF_REVIEW.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <input className="select" style={{ padding: "4px 8px", fontSize: 12, flex: 1, minWidth: 140 }} placeholder="note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn sm" disabled={busy} onClick={save}><Check size={13} /> Save</button>
      {current && current !== "pending" && <span className="muted" style={{ fontSize: 12 }}>current: {current.replace("_", " ")}</span>}
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
                    <td><b>{p.product_name}</b> <span className="dim mono">{p.sku ?? p.product_id}</span></td>
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

const SOURCE_PILL = { ai: ["AI", "violet"], ai_review: ["AI · check", "amber"], human: ["Reviewed", "green"], pending_llm: ["Not classified", "grey"] };

function SegmentDrawer({ segment: i, onClose, onChanged, toast }) {
  const mix = Object.entries(i.reason_breakdown).map(([k, v]) => ({
    label: reasonText(k), value: v, tone: ["UNCLASSIFIED", "UNCLEAR"].includes(k) ? "muted" : "",
  }));
  const seg = Object.entries(i.segment).map(([k, v]) => `${label(k)} ${v}`).join(", ") || "Whole product";
  const samples = i.sample_returns ?? i.sample_comments.map((c) => ({ comment: c, source: "pending_llm" }));
  return (
    <Overlay onClose={onClose} labelledBy="seg-title">
      <div className="dhead">
        <div>
          <span className="pill pink">{i.lift}× the shop average</span>
          <h2 id="seg-title" style={{ marginTop: 8 }}>{i.product_name} · {seg}</h2>
          <p className="muted" style={{ margin: "4px 0 0" }}>{i.sku ? `${i.sku} · ` : ""}{i.returns} of {i.orders} orders returned ({pct(i.return_rate)}) against a shop average of {pct(i.baseline_rate)}.</p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <Panel icon={Layers} title="Why these come back" subtitle="Dropdown reasons plus AI-read and reviewed comments">
        <HBars rows={mix} />
      </Panel>
      <Panel icon={MessageSquareText} title="What customers wrote" subtitle='"Other" comments and the reason given to each'>
        <div style={{ display: "grid", gap: 10 }}>
          {samples.length ? samples.map((x, n) => {
            const [txt, tone] = SOURCE_PILL[x.source] ?? ["", "grey"];
            return (
              <div className="quote" key={x.return_id ?? n} style={{ display: "grid", gap: 8 }}>
                <span>“{x.comment}”</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  {x.source !== "pending_llm" && <span className="pill violet">{reasonText(x.reason)}</span>}
                  {(x.detail || x.body_area) && <span className="muted" style={{ fontSize: 12 }}>{[x.detail, x.body_area].filter(Boolean).map(label).join(" · ")}</span>}
                  <span className={`pill ${tone}`}>{txt}</span>
                </div>
                {x.return_id && x.source !== "pending_llm" && x.source !== "human" &&
                  <ReviewControls returnId={x.return_id} aiCategory={x.reason} onChanged={onChanged} toast={toast} />}
              </div>
            );
          }) : <span className="muted">No comments for this segment.</span>}
        </div>
      </Panel>
      {i.unclassified_share > 0 && (
        <div className="callout amber"><PackageX size={18} />
          <p><b>{pct(i.unclassified_share, 0)} of these returns still have no real reason</b>Use "Classify with AI" on the Returns page to read them.</p></div>
      )}
    </Overlay>
  );
}

import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3, Bot, Clock, Gauge, IndianRupee, ListChecks, UserRound, Zap } from "lucide-react";
import { api } from "../api.js";
import { label, num, pct, useApi } from "../useApi.js";
import { ChartTip, Empty, ErrorBox, HBars, INTENT_TEXT, Panel, Skeleton, Stat } from "../components/ui.jsx";

const RESULT_COLOURS = { DRAFTED: "#8b7cf8", NEEDS_HUMAN: "#f2707e", NEEDS_INFO: "#f5b84a" };
const RESULT_TEXT = { DRAFTED: "Draft ready", NEEDS_HUMAN: "Needs a person", NEEDS_INFO: "Needs info" };

export default function CxMetrics() {
  const navigate = useNavigate();
  const m = useApi(() => api.cxMetrics(), []);

  if (m.loading) return <Panel><Skeleton rows={5} height={30} /></Panel>;
  if (m.error) return <ErrorBox error={m.error} onRetry={m.reload} />;
  const d = m.data;

  const intents = Object.entries(d.by_intent).map(([k, v]) => ({ name: INTENT_TEXT[k] ?? k, value: v })).sort((a, b) => b.value - a.value);
  const results = Object.entries(d.by_result).map(([k, v]) => ({ key: k, name: RESULT_TEXT[k] ?? k, value: v }));
  const statuses = Object.entries(d.tickets_by_status).map(([k, v]) => ({ label: label(k), value: v, tone: k === "ESCALATED" ? "pink" : k === "OPEN" ? "muted" : "" }));
  const actions = Object.entries(d.human_actions).map(([k, v]) => ({ label: label(k), value: v }));

  return (
    <div className="grid">
      <div className="grid stats">
        <Stat label="Copilot runs" value={num(d.analysed)} sub={`${d.fallback_runs} in fallback mode`} icon={Bot} />
        <Stat label="Approved as drafted" value={pct(d.acceptance_rate, 0)} sub="Of drafts an agent decided on" icon={Gauge} tone="green" />
        <Stat label="Avg run time" value={d.avg_latency_ms === null ? "–" : `${(d.avg_latency_ms / 1000).toFixed(1)} s`} sub="Ticket in → draft out" icon={Clock} tone="cyan" />
        <Stat label="AI cost" value={`$${d.total_cost_usd.toFixed(3)}`} sub={d.avg_cost_usd === null ? "No runs yet" : `$${d.avg_cost_usd.toFixed(4)} per run`} icon={IndianRupee} tone="amber" />
      </div>

      {d.analysed === 0 ? (
        <Panel>
          <Empty icon={BarChart3} title="No Copilot runs yet">
            Analyse a ticket in the inbox or run the 1-Click Demo, then come back.
            <div style={{ marginTop: 12 }}><button className="btn primary" onClick={() => navigate("/cx")}><Zap size={14} /> Go to inbox</button></div>
          </Empty>
        </Panel>
      ) : (
        <div className="grid two">
          <Panel icon={BarChart3} title="What customers ask" subtitle="Runs by intent">
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={intents} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="name" width={150} />
                  <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} content={<ChartTip render={(p) => <><b>{p.name}</b>{p.value} runs</>} />} />
                  <Bar dataKey="value" fill="#8b7cf8" isAnimationActive={false} radius={[0, 6, 6, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel icon={ListChecks} title="What Copilot did" subtitle="Result of each run">
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 200px) minmax(0, 1fr)", gap: 16, alignItems: "center" }}>
              <div style={{ height: 200 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={results} isAnimationActive={false} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3} stroke="none">
                      {results.map((r) => <Cell key={r.key} fill={RESULT_COLOURS[r.key] ?? "#5f6782"} />)}
                    </Pie>
                    <Tooltip content={<ChartTip render={(p) => <><b>{p.name}</b>{p.value} runs</>} />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: "grid", gap: 10 }}>
                {results.map((r) => (
                  <div key={r.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: RESULT_COLOURS[r.key] }} />
                    <span style={{ flex: 1 }}>{r.name}</span>
                    <b>{r.value}</b>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <Panel icon={ListChecks} title="Tickets by status">
            <HBars rows={statuses} />
          </Panel>

          <Panel icon={UserRound} title="Agent decisions" subtitle="What agents did with Copilot's results">
            {actions.length ? <HBars rows={actions} tone="pink" /> : <Empty title="No decisions yet">Approve, edit or escalate a result in the inbox.</Empty>}
          </Panel>
        </div>
      )}
    </div>
  );
}

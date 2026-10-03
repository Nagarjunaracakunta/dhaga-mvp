import { Cpu, Database, FileText, RefreshCw, Server, TriangleAlert } from "lucide-react";

export default function StatusBar({ health, error, onRefresh }) {
  if (error) {
    return (
      <div className="statusbar" role="status">
        <span className="item bad"><Server size={14} /> Backend not reachable.</span>
        <span>Start it with <span className="mono">uvicorn backend.main:app --reload</span></span>
        <span className="spacer" />
        <button className="btn ghost sm" onClick={onRefresh}><RefreshCw size={13} /> Retry</button>
      </div>
    );
  }
  if (!health) return <div className="statusbar"><span className="skeleton" style={{ height: 14, width: 420 }} /></div>;

  const supabase = health.cx_data_source === "supabase";
  return (
    <>
    {health.setup_issues?.length > 0 && (
      <div className="callout amber" role="alert">
        <TriangleAlert size={18} />
        <p><b>Setup needed</b>{health.setup_issues.join(" · ")}</p>
      </div>
    )}
    <div className="statusbar" role="status">
      <span className="item">
        <Database size={14} /> Data:
        <b className={health.database_reachable ? "ok" : "bad"}>
          {supabase ? "Supabase" : "Demo dataset"} · {health.database_reachable ? "connected" : "unreachable"}
        </b>
      </span>
      <span className="item">
        <Cpu size={14} /> AI:
        {health.llm_configured
          ? <b className="ok">Claude ready{health.llm_provider === "openrouter" ? " via OpenRouter" : ""} ({health.models.fast} + {health.models.strong})</b>
          : <b className="warn">Fallback mode · no API key (template replies)</b>}
      </span>
      <span className="item">
        <FileText size={14} /> Policies: <b>{health.policies_loaded.length} loaded</b>
      </span>
      <span className="spacer" />
      <span className="item dim"><Server size={14} /> FastAPI · Python</span>
    </div>
    </>
  );
}

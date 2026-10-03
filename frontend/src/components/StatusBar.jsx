import { RefreshCw, TriangleAlert } from "lucide-react";

// Compact system status for the sidebar footer.
export function SystemBox({ health, error, onRefresh }) {
  if (error) {
    return (
      <div className="sysbox" role="status">
        <div className="sysrow"><span className="led bad" /> Backend not reachable</div>
        <button className="btn ghost sm" style={{ color: "var(--side-ink)" }} onClick={onRefresh}><RefreshCw size={13} /> Retry</button>
      </div>
    );
  }
  if (!health) return <div className="sysbox"><div className="sysrow"><span className="led" /> Checking…</div></div>;

  const supabase = health.cx_data_source === "supabase";
  return (
    <div className="sysbox" role="status">
      <div className="sysrow">
        <span className={`led ${health.database_reachable ? "ok" : "bad"}`} />
        <span className="lbl">Data</span> {supabase ? "Supabase" : "Demo dataset"}
      </div>
      <div className="sysrow" title={health.llm_configured ? `${health.models.fast} + ${health.models.strong}` : "No API key: template replies"}>
        <span className={`led ${health.llm_configured ? "ok" : "warn"}`} />
        <span className="lbl">AI</span> {health.llm_configured ? `Claude${health.llm_provider === "openrouter" ? " · OpenRouter" : ""}` : "Fallback mode"}
      </div>
      <div className="sysrow">
        <span className={`led ${health.policies_loaded.length ? "ok" : "warn"}`} />
        <span className="lbl">Policies</span> {health.policies_loaded.length} loaded
      </div>
    </div>
  );
}

// Full-width banners at the top of the main area.
export function SystemBanner({ health, error }) {
  if (error) {
    return (
      <div className="callout red" role="alert">
        <TriangleAlert size={18} />
        <p><b>Backend not reachable</b>Start it with <span className="mono">uvicorn backend.main:app --reload</span></p>
      </div>
    );
  }
  if (health?.setup_issues?.length > 0) {
    return (
      <div className="callout amber" role="alert">
        <TriangleAlert size={18} />
        <p><b>Setup needed</b>{health.setup_issues.join(" · ")}</p>
      </div>
    );
  }
  if (health && !health.llm_configured) {
    return (
      <div className="callout amber" role="status">
        <TriangleAlert size={18} />
        <p><b>Fallback mode</b>No AI key is set, so Copilot uses keyword matching and template replies.</p>
      </div>
    );
  }
  return null;
}

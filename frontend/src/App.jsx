import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { BarChart3, Inbox, LayoutDashboard, RotateCcw, ShieldCheck, Shirt, Zap } from "lucide-react";
import { api } from "./api.js";
import StatusBar from "./components/StatusBar.jsx";
import DemoModal from "./components/DemoModal.jsx";
import Overview from "./pages/Overview.jsx";
import CxInbox from "./pages/CxInbox.jsx";
import CxMetrics from "./pages/CxMetrics.jsx";
import Returns from "./pages/Returns.jsx";
import DataQuality from "./pages/DataQuality.jsx";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/cx", label: "CX Inbox", icon: Inbox },
  { to: "/cx/metrics", label: "CX Metrics", icon: BarChart3 },
  { to: "/returns", label: "Returns", icon: RotateCcw },
  { to: "/returns/quality", label: "Data Quality", icon: ShieldCheck },
];

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0); // bump to make pages reload after the demo

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (e) {
      setHealthError(e);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    const id = setInterval(loadHealth, 30000);
    return () => clearInterval(id);
  }, [loadHealth]);

  const online = health && !healthError;

  return (
    <div className="shell">
      <header className="header">
        <div className="brand">
          <div className="brand-mark"><Shirt size={21} color="#fff" /></div>
          <div>
            <div className="brand-name">Dhaga &amp; Co. <span className="brand-badge">WORKBENCH</span></div>
            <div className="brand-sub">CX Copilot · Returns Insights</div>
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={15} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="header-actions">
          <button className="btn hot" onClick={() => setDemoOpen(true)} disabled={!online}>
            <Zap size={15} /> 1-Click Demo
          </button>
          <span className={`pill ${online ? (health.status === "ok" ? "green" : "amber") : "red"}`}>
            <span className="dot" /> {online ? (health.status === "ok" ? "System active" : "Degraded") : "Backend offline"}
          </span>
        </div>
      </header>

      <StatusBar health={health} error={healthError} onRefresh={loadHealth} />

      <Routes>
        <Route path="/" element={<Overview key={refreshKey} onDemo={() => setDemoOpen(true)} />} />
        <Route path="/cx" element={<CxInbox key={refreshKey} />} />
        <Route path="/cx/metrics" element={<CxMetrics key={refreshKey} />} />
        <Route path="/returns" element={<Returns />} />
        <Route path="/returns/quality" element={<DataQuality />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {demoOpen && (
        <DemoModal
          onClose={() => {
            setDemoOpen(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
}

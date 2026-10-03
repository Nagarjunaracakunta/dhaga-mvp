import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Gauge, LayoutGrid, MessagesSquare, PackageSearch, ShieldCheck, Spool, Zap } from "lucide-react";
import { api } from "./api.js";
import { SystemBanner, SystemBox } from "./components/StatusBar.jsx";
import DemoModal from "./components/DemoModal.jsx";
import Overview from "./pages/Overview.jsx";
import CxInbox from "./pages/CxInbox.jsx";
import CxMetrics from "./pages/CxMetrics.jsx";
import Returns from "./pages/Returns.jsx";
import DataQuality from "./pages/DataQuality.jsx";

const NAV = [
  { group: "Today", items: [{ to: "/", label: "Overview", icon: LayoutGrid }] },
  {
    group: "Customer support",
    items: [
      { to: "/cx", label: "Support inbox", icon: MessagesSquare },
      { to: "/cx/metrics", label: "Copilot metrics", icon: Gauge },
    ],
  },
  {
    group: "Returns",
    items: [
      { to: "/returns", label: "Return insights", icon: PackageSearch },
      { to: "/returns/quality", label: "Data quality", icon: ShieldCheck },
    ],
  },
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
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Spool size={20} /></div>
          <div>
            <div className="brand-name">Dhaga &amp; Co.</div>
            <div className="brand-sub">Operations workbench</div>
          </div>
        </div>
        {NAV.map(({ group, items }) => (
          <nav key={group} className="navgroup" aria-label={group}>
            <div className="navgroup-label">{group}</div>
            {items.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
                <Icon size={16} /> {label}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="spacer" />
        <button className="btn side" onClick={() => setDemoOpen(true)} disabled={!online}>
          <Zap size={15} /> Run the demo
        </button>
        <SystemBox health={health} error={healthError} onRefresh={loadHealth} />
      </aside>

      <main className="content">
      <SystemBanner health={health} error={healthError} />

      <Routes>
        <Route path="/" element={<Overview key={refreshKey} onDemo={() => setDemoOpen(true)} />} />
        <Route path="/cx" element={<CxInbox key={refreshKey} />} />
        <Route path="/cx/metrics" element={<CxMetrics key={refreshKey} />} />
        <Route path="/returns" element={<Returns />} />
        <Route path="/returns/quality" element={<DataQuality />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </main>

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

import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { AUTH_LOST_EVENT, getCurrentOperator, getHealth, signOut } from "./api";
import type { HealthResponse, Operator } from "./types";
import { DelayMappingView } from "./DelayMappingView";
import { HomeDashboardView } from "./HomeDashboardView";
import { LoginView } from "./LoginView";
import { OperatorsView } from "./OperatorsView";
import { PlanGeneratorView } from "./PlanGeneratorView";
import { SowAnalyzerView } from "./SowAnalyzerView";
import { RetrospectiveView } from "./RetrospectiveView";
import { WsrDashboardView } from "./WsrDashboardView";
import { ShellMetaContext } from "./shellMeta";
import { requestWsrReset } from "./wsrSession";
import { ProjectPulseLogo } from "./components/ProjectPulseLogo";

const NAV_HIDDEN_KEY = "projectpulse.nav-hidden";

const MODULES: { path: string; label: string; icon: string; resetWsr?: boolean }[] = [
  { path: "/sow", label: "SOW Analyzer", icon: "analytics" },
  { path: "/wsr", label: "WSR & Insights", icon: "insights", resetWsr: true },
  { path: "/delay-mapping", label: "Delay Mapping", icon: "table_view" },
];

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/wsr": "Generate WSR",
  "/delay-mapping": "Delay Mapping",
  "/wsr/delay-mapping": "Delay Mapping",
  "/sow": "SOW Analyzer",
  "/plan": "Project Plan Builder",
  "/retrospective": "Retrospective",
  "/operators": "Operators",
};

function Glyph({ name, filled }: { name: string; filled?: boolean }) {
  return (
    <span
      className={`material-symbols-outlined${filled ? " icon-fill-1" : ""}`}
      aria-hidden="true"
    >
      {name}
    </span>
  );
}

function readNavHidden(): boolean {
  try {
    return localStorage.getItem(NAV_HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [operator, setOperator] = useState<Operator | null>(null);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [pageMeta, setPageMeta] = useState("");
  const [navHidden, setNavHidden] = useState(readNavHidden);
  const location = useLocation();

  useEffect(() => {
    setPageMeta("");
  }, [location.pathname]);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!health) {
      return;
    }
    if (!health.auth_required) {
      setSessionChecked(true);
      return;
    }
    getCurrentOperator()
      .then(setOperator)
      .catch(() => setOperator(null))
      .finally(() => setSessionChecked(true));
  }, [health]);

  useEffect(() => {
    const onLost = () => setOperator(null);
    window.addEventListener(AUTH_LOST_EVENT, onLost);
    return () => window.removeEventListener(AUTH_LOST_EVENT, onLost);
  }, []);

  function toggleNav() {
    setNavHidden((hidden) => {
      const next = !hidden;
      try {
        localStorage.setItem(NAV_HIDDEN_KEY, next ? "1" : "0");
      } catch {
        // Ignore storage errors; the toggle still works for this session.
      }
      return next;
    });
  }

  const locked = Boolean(health?.auth_required && sessionChecked && !operator);
  const title = TITLES[location.pathname] ?? "Project Automation";

  if (locked) {
    return (
      <div className="shell-login">
        <LoginView onSignedIn={setOperator} />
      </div>
    );
  }

  return (
    <ShellMetaContext.Provider value={setPageMeta}>
      <div className={navHidden ? "shell nav-hidden" : "shell"}>
        <aside className="sidebar" aria-hidden={navHidden} inert={navHidden}>
          <Link to="/" className="brand" aria-label="ProjectPulse home">
            <ProjectPulseLogo variant="mark" className="brand-logo" decorative />
            <div>
              <strong>ProjectPulse</strong>
              <p>Project Intelligence Platform</p>
            </div>
          </Link>
          <nav>
            {MODULES.map((module) => (
              <NavLink
                key={module.path}
                to={module.path}
                end={module.path === "/wsr"}
                className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
                onClick={() => {
                  if (module.resetWsr) {
                    requestWsrReset();
                  }
                }}
              >
                {({ isActive }) => (
                  <>
                    <Glyph name={module.icon} filled={isActive && module.path === "/wsr"} />
                    {module.label}
                  </>
                )}
              </NavLink>
            ))}
            {operator?.role === "admin" ? (
              <NavLink
                to="/operators"
                className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              >
                <Glyph name="manage_accounts" />
                Operators
              </NavLink>
            ) : null}
          </nav>
          <div className="sidebar-foot">
            <button type="button" className="nav-hide" onClick={toggleNav}>
              <Glyph name="left_panel_close" />
              Hide navigation
            </button>
          </div>
        </aside>
        <div className="shell-main">
          <header className="shell-top">
            <div className="shell-top-lead">
              <button
                type="button"
                className="shell-nav-toggle"
                onClick={toggleNav}
                aria-pressed={navHidden}
                aria-label={navHidden ? "Show navigation" : "Hide navigation"}
              >
                <span className="material-symbols-outlined">
                  {navHidden ? "left_panel_open" : "left_panel_close"}
                </span>
              </button>
              <Link to="/" className="shell-home" aria-label="Project Management Dashboard">
                <span className="material-symbols-outlined">dashboard</span>
              </Link>
              <span className="shell-tab">{title}</span>
            </div>
            <div className="shell-top-end">
              {pageMeta ? <p className="status">{pageMeta}</p> : null}
              {operator ? (
                <button
                  type="button"
                  className="linkish"
                  onClick={() => {
                    signOut().finally(() => setOperator(null));
                  }}
                >
                  Sign out
                </button>
              ) : null}
            </div>
          </header>
          <main className="shell-content">
            {health?.auth_required && !sessionChecked ? <p>Checking session…</p> : null}
            <Routes>
              <Route path="/" element={<HomeDashboardView />} />
              <Route path="/sow" element={<SowAnalyzerView />} />
              <Route path="/plan" element={<PlanGeneratorView />} />
              <Route path="/wsr" element={<WsrDashboardView />} />
              <Route path="/delay-mapping" element={<DelayMappingView />} />
              <Route path="/wsr/delay-mapping" element={<Navigate to="/delay-mapping" replace />} />
              <Route path="/retrospective" element={<RetrospectiveView />} />
              <Route
                path="/operators"
                element={operator?.role === "admin" ? <OperatorsView /> : <Navigate to="/" replace />}
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </ShellMetaContext.Provider>
  );
}

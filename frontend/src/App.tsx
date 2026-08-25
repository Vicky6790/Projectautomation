import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { AUTH_LOST_EVENT, getCurrentOperator, getHealth, signOut } from "./api";
import type { HealthResponse, Module, Operator } from "./types";
import { LoginView } from "./LoginView";
import { OperatorsView } from "./OperatorsView";
import { PlanGeneratorView } from "./PlanGeneratorView";
import { SowAnalyzerView } from "./SowAnalyzerView";
import { RetrospectiveView } from "./RetrospectiveView";
import { WsrDashboardView } from "./WsrDashboardView";
import { ShellMetaContext } from "./shellMeta";

const MODULES: { id: Module; label: string; icon: string }[] = [
  { id: "sow", label: "SOW Analyzer", icon: "M4 6h16M4 12h10M4 18h14" },
  { id: "plan", label: "Project Plan Builder", icon: "M4 7h16M4 12h16M4 17h8" },
  { id: "wsr", label: "WSR & Insights", icon: "M4 19V5m4 14V9m4 10V7m4 12v-6" },
  { id: "retrospective", label: "Retrospective", icon: "M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
];

const TITLES: Record<string, string> = {
  "/wsr": "Generate WSR",
  "/sow": "SOW Analyzer",
  "/plan": "Project Plan Builder",
  "/retrospective": "Retrospective",
  "/operators": "Operators",
};

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [operator, setOperator] = useState<Operator | null>(null);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [pageMeta, setPageMeta] = useState("");
  const location = useLocation();

  useEffect(() => {
    setPageMeta("");
  }, [location.pathname]);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error: unknown) => {
        setHealthError(error instanceof Error ? error.message : "API unreachable");
      });
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

  const locked = Boolean(health?.auth_required && sessionChecked && !operator);
  const title = TITLES[location.pathname] ?? "Project Automation";
  const sessionLabel = operator
    ? operator.username
    : health?.auth_mode === "disabled"
      ? "Local session"
      : "";

  if (locked) {
    return (
      <div className="shell-login">
        <LoginView onSignedIn={setOperator} />
      </div>
    );
  }

  return (
    <ShellMetaContext.Provider value={setPageMeta}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-mark">PA</span>
            <div>
              <strong>Project Automation</strong>
              <p>Project Intelligence Platform</p>
            </div>
          </div>
          <nav>
            {MODULES.map((module) => (
              <NavLink
                key={module.id}
                to={`/${module.id}`}
                className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              >
                <Icon path={module.icon} />
                {module.label}
              </NavLink>
            ))}
            {operator?.role === "admin" ? (
              <NavLink
                to="/operators"
                className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              >
                <Icon path="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 7a4 4 0 108 0 4 4 0 00-8 0M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
                Operators
              </NavLink>
            ) : null}
          </nav>
          <div className="sidebar-foot">
            <p className="status">{health ? `API ${health.status}` : (healthError ?? "Checking API…")}</p>
            <span className="nav-item muted-item">User Profile</span>
            <span className="nav-item muted-item">{sessionLabel || "Signed in locally"}</span>
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
        </aside>
        <div className="shell-main">
          <header className="shell-top">
            <h1>{title}</h1>
            <p className="status">{pageMeta || sessionLabel}</p>
          </header>
          <main className="shell-content">
            {health?.auth_required && !sessionChecked ? <p>Checking session…</p> : null}
            <Routes>
              <Route path="/" element={<Navigate to="/wsr" replace />} />
              <Route path="/sow" element={<SowAnalyzerView />} />
              <Route path="/plan" element={<PlanGeneratorView />} />
              <Route path="/wsr" element={<WsrDashboardView />} />
              <Route path="/retrospective" element={<RetrospectiveView />} />
              <Route
                path="/operators"
                element={operator?.role === "admin" ? <OperatorsView /> : <Navigate to="/wsr" replace />}
              />
            </Routes>
          </main>
        </div>
      </div>
    </ShellMetaContext.Provider>
  );
}

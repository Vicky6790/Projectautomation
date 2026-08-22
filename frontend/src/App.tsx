import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { AUTH_LOST_EVENT, getCurrentOperator, getHealth, signOut } from "./api";
import type { HealthResponse, Module, Operator } from "./types";
import { LoginView } from "./LoginView";
import { OperatorsView } from "./OperatorsView";
import { PlanGeneratorView } from "./PlanGeneratorView";
import { SowAnalyzerView } from "./SowAnalyzerView";
import { RetrospectiveView } from "./RetrospectiveView";
import { WsrDashboardView } from "./WsrDashboardView";

const MODULES: { id: Module; label: string }[] = [
  { id: "sow", label: "SOW Analyzer" },
  { id: "plan", label: "Plan Generator" },
  { id: "wsr", label: "Weekly Status" },
  { id: "retrospective", label: "Retrospective" },
];

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [operator, setOperator] = useState<Operator | null>(null);
  const [sessionChecked, setSessionChecked] = useState(false);

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

  return (
    <div className="app">
      <header className="topbar">
        <h1>Project Automation</h1>
        <p className="status">
          {health
            ? `API ${health.status} · auth ${health.auth_mode}`
            : (healthError ?? "Checking API…")}
          {operator ? ` · ${operator.username}` : ""}
        </p>
        {operator ? (
          <button
            type="button"
            onClick={() => {
              signOut().finally(() => setOperator(null));
            }}
          >
            Sign out
          </button>
        ) : null}
        {!locked ? (
          <nav>
            {MODULES.map((module) => (
              <NavLink key={module.id} to={`/${module.id}`}>
                {module.label}
              </NavLink>
            ))}
            {operator?.role === "admin" ? <NavLink to="/operators">Operators</NavLink> : null}
          </nav>
        ) : null}
      </header>
      <main>
        {health?.auth_required && !sessionChecked ? <p>Checking session…</p> : null}
        {locked ? (
          <LoginView onSignedIn={setOperator} />
        ) : (
          <Routes>
            <Route path="/" element={<Navigate to="/sow" replace />} />
            <Route path="/sow" element={<SowAnalyzerView />} />
            <Route path="/plan" element={<PlanGeneratorView />} />
            <Route path="/wsr" element={<WsrDashboardView />} />
            <Route path="/retrospective" element={<RetrospectiveView />} />
            <Route
              path="/operators"
              element={operator?.role === "admin" ? <OperatorsView /> : <Navigate to="/sow" replace />}
            />
          </Routes>
        )}
      </main>
    </div>
  );
}

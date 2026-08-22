import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth } from "./api";
import type { HealthResponse, Module } from "./types";
import { ModulePage } from "./ModulePage";
import { SowAnalyzerView } from "./SowAnalyzerView";

const MODULES: { id: Module; label: string }[] = [
  { id: "sow", label: "SOW Analyzer" },
  { id: "plan", label: "Plan Generator" },
  { id: "wsr", label: "Weekly Status" },
  { id: "retrospective", label: "Retrospective" },
];

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error: unknown) => {
        setHealthError(error instanceof Error ? error.message : "API unreachable");
      });
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <h1>Project Automation</h1>
        <p className="status">
          {health
            ? `API ${health.status} · auth ${health.auth_mode}`
            : (healthError ?? "Checking API…")}
        </p>
        <nav>
          {MODULES.map((module) => (
            <NavLink key={module.id} to={`/${module.id}`}>
              {module.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/sow" replace />} />
          <Route path="/sow" element={<SowAnalyzerView />} />
          {MODULES.filter((module) => module.id !== "sow").map((module) => (
            <Route
              key={module.id}
              path={`/${module.id}`}
              element={<ModulePage module={module.id} title={module.label} />}
            />
          ))}
        </Routes>
      </main>
    </div>
  );
}

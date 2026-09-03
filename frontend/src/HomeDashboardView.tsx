import { Link } from "react-router-dom";

const MODULES = [
  {
    to: "/sow",
    tone: "sow",
    icon: "analytics",
    kicker: "Start here",
    title: "SOW Analyzer",
    detail: "Turn the signed statement of work into risks, gray areas, and questions the team can act on.",
    points: ["Gray areas & gaps", "Delivery risks", "Clarification questions"],
    cta: "Analyze SOW",
  },
  {
    to: "/wsr",
    tone: "wsr",
    icon: "insights",
    kicker: "Weekly pulse",
    title: "WSR & Insights",
    detail: "Upload the current MPP and publish a weekly status grounded in Baseline vs Current.",
    points: ["Go-Live shift", "Narrative insights", "MPP-backed facts"],
    cta: "Generate WSR",
  },
  {
    to: "/delay-mapping",
    tone: "delay",
    icon: "table_view",
    kicker: "Go-Live drivers",
    title: "Delay Mapping",
    detail: "List Delay and Additional tasks that actually move Go-Live, with working-day impact.",
    points: ["Delay vs Additional", "Working-day shift", "Exportable sheet"],
    cta: "Map delays",
  },
] as const;

export function HomeDashboardView() {
  return (
    <section className="home-dash">
      <header className="home-hero">
        <p className="home-kicker">Dashboard</p>
        <h1>Delivery Intelligence from the Signed SOW to Go-Live</h1>
        <p className="home-lead">
          Review the signed SOW, publish weekly status, and map the tasks that actually move Go-Live.
          Every fact comes from the live MPP — missing values stay Unavailable.
        </p>
      </header>

      <ul className="home-modules">
        {MODULES.map((module, index) => (
          <li key={module.to} style={{ animationDelay: `${80 + index * 70}ms` }}>
            <Link to={module.to} className={`home-mod home-mod-${module.tone}`}>
              <span className="home-mod-icon" aria-hidden="true">
                <span className="material-symbols-outlined">{module.icon}</span>
              </span>
              <span className="home-mod-num">{String(index + 1).padStart(2, "0")}</span>
              <p className="home-mod-kicker">{module.kicker}</p>
              <strong>{module.title}</strong>
              <span className="home-mod-detail">{module.detail}</span>
              <ul>
                {module.points.map((point) => (
                  <li key={point}>
                    <span className="material-symbols-outlined" aria-hidden="true">
                      check_circle
                    </span>
                    {point}
                  </li>
                ))}
              </ul>
              <span className="home-mod-cta">
                {module.cta}
                <span className="material-symbols-outlined">arrow_forward</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <ol className="home-path" aria-label="How the workspace flows">
        <li>
          <span className="home-path-icon" aria-hidden="true">
            <span className="material-symbols-outlined">description</span>
          </span>
          <strong>Read the SOW</strong>
          <span>Surface gaps before they become schedule noise.</span>
        </li>
        <li>
          <span className="home-path-icon" aria-hidden="true">
            <span className="material-symbols-outlined">upload_file</span>
          </span>
          <strong>Upload the live MPP</strong>
          <span>Weekly status and delay mapping both read the same plan.</span>
        </li>
        <li>
          <span className="home-path-icon" aria-hidden="true">
            <span className="material-symbols-outlined">share</span>
          </span>
          <strong>Share the facts</strong>
          <span>Download the WSR or export the Go-Live delay sheet.</span>
        </li>
      </ol>
    </section>
  );
}

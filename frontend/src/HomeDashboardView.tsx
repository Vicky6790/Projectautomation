import { Link } from "react-router-dom";

const STEPS = [
  {
    to: "/sow",
    icon: "analytics",
    title: "SOW Analyzer",
    hint: "Read the signed statement of work",
    detail: "Extract risks, gray areas, missing requirements, and clarification questions from the SOW.",
  },
  {
    to: "/plan",
    icon: "format_list_bulleted",
    title: "Project Plan Builder",
    hint: "Turn scope into a schedule",
    detail: "Select phases and deliverables, then generate an MPP the team can open in Microsoft Project.",
  },
  {
    to: "/wsr",
    icon: "insights",
    title: "WSR & Insights",
    hint: "Report from the live plan",
    detail: "Upload the current MPP to produce the weekly status and Go-Live shift.",
  },
  {
    to: "/delay-mapping",
    icon: "table_view",
    title: "Delay Mapping",
    hint: "Baseline vs current variance",
    detail: "See delayed work, newly added tasks, and what actually moved Go-Live.",
  },
  {
    to: "/retrospective",
    icon: "history",
    title: "Retrospective",
    hint: "Close the delivery loop",
    detail: "Review schedule variance, milestone delivery, what went well, and lessons from the same plan.",
  },
] as const;

export function HomeDashboardView() {
  return (
    <section className="home-dash">
      <div className="home-hero">
        <div className="home-hero-mark" aria-hidden="true">
          <span className="material-symbols-outlined">dashboard</span>
        </div>
        <div>
          <p className="home-kicker">Project Automation</p>
          <h1>Welcome to Project Management Dashboard</h1>
          <p className="home-lead">
            One workspace for the delivery path: analyze the SOW, build the plan, publish the weekly
            status, then capture the retrospective.
          </p>
        </div>
      </div>

      <div className="home-scene" aria-hidden="true">
        <svg viewBox="0 0 960 160" role="presentation">
          <defs>
            <linearGradient id="home-line" x1="0" x2="1">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="50%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#f59e0b" />
            </linearGradient>
          </defs>
          <path
            className="home-scene-path"
            d="M80 80 H880"
            fill="none"
            stroke="url(#home-line)"
            strokeWidth="3"
            strokeDasharray="8 10"
            strokeLinecap="round"
          />
          <g transform="translate(80 80)">
            <g className="home-scene-node">
              <circle r="28" fill="#eef2ff" stroke="#4f46e5" strokeWidth="2" />
              <text textAnchor="middle" y="6" fontSize="13" fontWeight="700" fill="#4338ca">
                SOW
              </text>
            </g>
          </g>
          <g transform="translate(347 80)">
            <g className="home-scene-node">
              <circle r="28" fill="#e0f2fe" stroke="#0284c7" strokeWidth="2" />
              <text textAnchor="middle" y="6" fontSize="13" fontWeight="700" fill="#0369a1">
                Plan
              </text>
            </g>
          </g>
          <g transform="translate(613 80)">
            <g className="home-scene-node">
              <circle r="28" fill="#d1fae5" stroke="#059669" strokeWidth="2" />
              <text textAnchor="middle" y="6" fontSize="13" fontWeight="700" fill="#047857">
                WSR
              </text>
            </g>
          </g>
          <g transform="translate(880 80)">
            <g className="home-scene-node">
              <circle r="28" fill="#fef3c7" stroke="#d97706" strokeWidth="2" />
              <text textAnchor="middle" y="6" fontSize="12" fontWeight="700" fill="#b45309">
                Retro
              </text>
            </g>
          </g>
        </svg>
      </div>

      <ol className="home-flow" aria-label="Application workflow">
        {STEPS.map((step, index) => (
          <li key={step.to} className="home-flow-item" style={{ animationDelay: `${index * 120}ms` }}>
            <Link to={step.to} className="home-step">
              <span className="home-step-icon" aria-hidden="true">
                <span className="material-symbols-outlined">{step.icon}</span>
              </span>
              <span className="home-step-copy">
                <strong>{step.title}</strong>
                <em>{step.hint}</em>
                <span>{step.detail}</span>
              </span>
            </Link>
            {index < STEPS.length - 1 ? (
              <span className="home-flow-arrow" aria-hidden="true">
                <span className="material-symbols-outlined">arrow_forward</span>
              </span>
            ) : null}
          </li>
        ))}
      </ol>

      <ul className="home-tiles">
        {STEPS.map((step) => (
          <li key={`${step.to}-tile`}>
            <Link to={step.to} className="home-tile">
              <span className="home-tile-art" aria-hidden="true" data-step={step.to.slice(1)}>
                <span className="material-symbols-outlined">{step.icon}</span>
              </span>
              <strong>{step.title}</strong>
              <span>{step.detail}</span>
              <span className="home-tile-cta">
                Open
                <span className="material-symbols-outlined">chevron_right</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

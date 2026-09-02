import type { ReactNode } from "react";

export type ModuleTone = "sow" | "wsr" | "delay";

const PREVIEWS: Record<ModuleTone, { icon: string; label: string; hint: string; fill: string }[]> = {
  sow: [
    { icon: "warning", label: "Risks", hint: "Flagged in the signed SOW", fill: "78%" },
    { icon: "quiz", label: "Questions", hint: "Need a decision before delivery", fill: "64%" },
    { icon: "account_tree", label: "Dependencies", hint: "External waits in the contract", fill: "52%" },
  ],
  wsr: [
    { icon: "event", label: "Go-Live", hint: "Baseline vs Current shift", fill: "82%" },
    { icon: "percent", label: "Progress", hint: "Plan-backed completion", fill: "61%" },
    { icon: "timeline", label: "Timeline", hint: "This week and next week", fill: "48%" },
  ],
  delay: [
    { icon: "event_busy", label: "Delay", hint: "Tagged in the project plan", fill: "74%" },
    { icon: "add_circle", label: "Additional", hint: "Inserted work on the path", fill: "58%" },
    { icon: "flag", label: "Go-Live", hint: "Working-day impact", fill: "40%" },
  ],
};

export function ModuleHero({
  tone,
  icon,
  kicker,
  title,
  subtitle,
  actions,
}: {
  tone: ModuleTone;
  icon: string;
  kicker: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <header className={`mod-hero mod-hero-${tone}`}>
      <span className="mod-icon" aria-hidden="true">
        <span className="material-symbols-outlined">{icon}</span>
      </span>
      <div className="mod-hero-copy">
        <p className="mod-kicker">{kicker}</p>
        <h1>{title}</h1>
        <p className="mod-hero-sub">{subtitle}</p>
      </div>
      {actions ? <div className="mod-hero-actions dms-no-print">{actions}</div> : null}
    </header>
  );
}

export function ModuleLanding({
  tone,
  steps,
  children,
}: {
  tone: ModuleTone;
  steps: { icon: string; title: string; copy: string }[];
  children?: ReactNode;
}) {
  return (
    <div className={`mod-landing mod-landing-${tone} dms-no-print`}>
      <article className="mod-landing-copy">
        <ol className="mod-steps">
          {steps.map((step, index) => (
            <li key={step.title} style={{ animationDelay: `${index * 80}ms` }}>
              <span className="mod-step-icon" aria-hidden="true">
                <span className="material-symbols-outlined">{step.icon}</span>
              </span>
              <strong>{step.title}</strong>
              <span>{step.copy}</span>
            </li>
          ))}
        </ol>
      </article>
      {children ? <div className="mod-landing-aside">{children}</div> : <ModuleShowcase tone={tone} />}
    </div>
  );
}

function ModuleShowcase({ tone }: { tone: ModuleTone }) {
  return (
    <aside className="mod-preview">
      <p className="mod-preview-kicker">What you get</p>
      <ul>
        {PREVIEWS[tone].map((item, index) => (
          <li key={item.label} style={{ animationDelay: `${120 + index * 90}ms` }}>
            <span className="mod-preview-icon" aria-hidden="true">
              <span className="material-symbols-outlined">{item.icon}</span>
            </span>
            <div>
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
              <span className="mod-preview-bar">
                <i style={{ width: item.fill, animationDelay: `${280 + index * 90}ms` }} />
              </span>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

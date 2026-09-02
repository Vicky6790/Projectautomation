import type { ReactNode } from "react";

export type ModuleTone = "sow" | "wsr" | "delay";

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
      <span className="mod-orb" aria-hidden="true">
        <span className="mod-orb-ring" />
        <span className="mod-orb-ring" />
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
            <li key={step.title} style={{ animationDelay: `${index * 90}ms` }}>
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
  if (tone === "sow") {
    return (
      <aside className="mod-showcase" aria-hidden="true">
        <div className="mod-float mod-float-a">
          <span className="material-symbols-outlined">warning</span>
          Risks
        </div>
        <div className="mod-float mod-float-b">
          <span className="material-symbols-outlined">quiz</span>
          Questions
        </div>
        <div className="mod-float mod-float-c">
          <span className="material-symbols-outlined">account_tree</span>
          Dependencies
        </div>
      </aside>
    );
  }
  if (tone === "wsr") {
    return (
      <aside className="mod-showcase" aria-hidden="true">
        <div className="mod-float mod-float-a">
          <span className="material-symbols-outlined">event</span>
          Go-Live
        </div>
        <div className="mod-float mod-float-b">
          <span className="material-symbols-outlined">percent</span>
          Progress
        </div>
        <div className="mod-float mod-float-c">
          <span className="material-symbols-outlined">timeline</span>
          Timeline
        </div>
      </aside>
    );
  }
  return (
    <aside className="mod-showcase" aria-hidden="true">
      <div className="mod-float mod-float-a">
        <span className="material-symbols-outlined">event_busy</span>
        Delay
      </div>
      <div className="mod-float mod-float-b">
        <span className="material-symbols-outlined">add_circle</span>
        Additional
      </div>
      <div className="mod-float mod-float-c">
        <span className="material-symbols-outlined">flag</span>
        Go-Live
      </div>
    </aside>
  );
}

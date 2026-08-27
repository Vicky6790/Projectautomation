import { useContext, useEffect, useState, type ReactNode } from "react";
import { generateWsr, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { WsrGantt } from "./components/WsrGantt";
import { WsrProgressRing } from "./components/WsrProgressRing";
import { ShellMetaContext } from "./shellMeta";
import type {
  AiDerivedItem,
  ExecutiveSummary,
  FileRecord,
  MilestoneItem,
  PhaseStatus,
  ProcessingResponse,
  ProgressItem,
  StatusReport,
  WsrPlanFacts,
} from "./types";
import {
  healthLabel,
  personDaysLabel,
  percent,
  phaseState,
  phaseWbs,
  shortDate,
  splitInsight,
  unavailable,
  windowRange,
} from "./wsrFormat";

const GENERATE_STAGES = [
  "Reading the file",
  "Extracting plan values",
  "Creating narrative",
  "Rendering the report",
];

const KPI_TONES = ["kpi-indigo", "kpi-emerald", "kpi-amber", "kpi-blue"] as const;
const KPI_ICONS = ["calendar_today", "person_add", "schedule", "assignment"] as const;

function asReport(result: ProcessingResponse["result"]): StatusReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as StatusReport;
  return {
    as_of_date: data.as_of_date ?? null,
    generated_at: data.generated_at ?? null,
    planned_only: Boolean(data.planned_only),
    exportable: Boolean(data.exportable),
    project_health: data.project_health ?? data.facts?.project_health ?? null,
    facts: data.facts ?? null,
    progress: data.progress ?? [],
    milestones: data.milestones ?? [],
    client_needs: data.client_needs ?? [],
    risks: data.risks ?? [],
    issues: data.issues ?? [],
    dependencies: data.dependencies ?? [],
    management_attention: data.management_attention ?? [],
    decisions_required: data.decisions_required ?? [],
    next_7_day_priorities: data.next_7_day_priorities ?? [],
  };
}

function visibleInsights(items: AiDerivedItem[]): AiDerivedItem[] {
  return items.filter((item) => item.review_status !== "removed");
}

function isSameDay(date: string | null | undefined, asOf: string | null | undefined): boolean {
  if (!date || !asOf) {
    return false;
  }
  return date.slice(0, 10) === asOf.slice(0, 10);
}

function Section({
  n,
  title,
  hint,
  children,
  flush,
}: {
  n: number;
  title: string;
  hint?: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className={`wsr-section${flush ? " wsr-section-flush" : ""}`}>
      <div className="wsr-section-head">
        <h3>
          <span className="wsr-num">{n}</span>
          {title}
        </h3>
        {hint ? <p className="muted">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

function KpiCard({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: string;
  tone: string;
}) {
  return (
    <article className={`kpi-card ${tone}`}>
      <div className="kpi-icon">
        <span className="material-symbols-outlined" aria-hidden="true">
          {icon}
        </span>
      </div>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {hint ? <p className="metric-hint">{hint}</p> : null}
    </article>
  );
}

function InsightCards({
  items,
  tone,
  empty,
}: {
  items: AiDerivedItem[];
  tone: "need" | "risk";
  empty: string;
}) {
  if (!items.length) {
    return <p>{empty}</p>;
  }
  return (
    <div className="insight-grid">
      {items.map((item) => {
        const { title, body } = splitInsight(item.content);
        return (
          <article key={item.id} className={`insight-card insight-${tone}`}>
            <h4>
              <span className="material-symbols-outlined" aria-hidden="true">
                {tone === "need" ? "description" : "warning"}
              </span>
              {title}
            </h4>
            {body ? (
              <ul>
                <li>{body}</li>
              </ul>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

export function WsrDashboardView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [message, setMessage] = useState(
    "Upload a Microsoft Project (.mpp) file, then generate WSR & Insights.",
  );

  const report = asReport(job?.result ?? null);
  const facts: WsrPlanFacts = report?.facts ?? {};

  useEffect(() => {
    const identity = [facts.project_name, facts.project_owner].filter(Boolean).join(" · ");
    setPageMeta(identity);
    return () => setPageMeta("");
  }, [facts.project_name, facts.project_owner, setPageMeta]);

  useEffect(() => {
    if (!busy) {
      setStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStage((current) => Math.min(current + 1, GENERATE_STAGES.length - 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function runGenerate(handle: string) {
    setBusy(true);
    setMessage("Reading the file, extracting plan values, creating narrative, and rendering the report…");
    try {
      const result = await generateWsr(handle);
      setJob(result);
      setMessage(result.status === "succeeded" ? "Status report ready." : "Generation failed.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!uploaded) {
      return;
    }
    setBusy(true);
    try {
      await retryJob("wsr", uploaded.id);
    } catch {
      // Generate re-runs a failed handle even if retry is not needed.
    }
    await runGenerate(uploaded.id);
  }

  function printForMeeting() {
    document.documentElement.classList.add("wsr-printing");
    const cleanup = () => document.documentElement.classList.remove("wsr-printing");
    window.addEventListener("afterprint", cleanup, { once: true });
    window.setTimeout(() => window.print(), 50);
  }

  const deployed = facts.resources_deployed ?? facts.people_planned;
  const kpis = [
    {
      label: "Phases to Go-Live",
      value: unavailable(facts.phase_count),
      hint: "Across project lifecycle",
    },
    {
      label: "Resources Deployed",
      value: unavailable(deployed),
      hint: "From Resource Sheet",
    },
    {
      label: "Person-Days Planned",
      value: personDaysLabel(facts.person_days_planned),
      hint: "Total effort estimated",
    },
    {
      label: "Work Items Complete",
      value: unavailable(facts.completed_work_items),
      hint:
        facts.planned_work_items != null
          ? `of ${facts.planned_work_items} planned`
          : "of planned work items",
    },
  ];

  return (
    <section className="wsr-page">
      <header className="wsr-page-head">
        <h2>WSR & Insights</h2>
        <p>Generate comprehensive status reports from your project plan.</p>
      </header>

      <div className="wsr-upload-card">
        <div className="wsr-upload-inner">
          {uploaded ? (
            <div className="file-chip">
              <span className="wsr-upload-icon" aria-hidden="true">
                <span className="material-symbols-outlined">description</span>
              </span>
              <div>
                <p className="wsr-upload-title">{uploaded.filename}</p>
                <p className="wsr-upload-hint">Microsoft Project (.mpp)</p>
              </div>
              <button
                type="button"
                className="chip-clear"
                aria-label="Remove file"
                disabled={busy}
                onClick={() => {
                  setUploaded(null);
                  setJob(null);
                  setMessage("Upload a Microsoft Project (.mpp) file, then generate WSR & Insights.");
                }}
              >
                ×
              </button>
            </div>
          ) : (
            <FileUploader
              variant="card"
              disabled={busy}
              accept=".mpp,application/vnd.ms-project"
              label="Upload Project Plan"
              hint="Microsoft Project (.mpp)"
              endpoint="/api/v1/wsr/uploads"
              onUploaded={(file) => {
                setUploaded(file);
                setJob(null);
                setMessage("File ready. Generate WSR & Insights to build the dashboard.");
              }}
              onError={setMessage}
            />
          )}
          <div className="wsr-action-buttons">
            <button
              type="button"
              className="btn btn-outline"
              disabled={!report || busy}
              onClick={printForMeeting}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                download
              </span>
              Download to PDF
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!uploaded || busy}
              onClick={() => uploaded && void runGenerate(uploaded.id)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                insights
              </span>
              Generate WSR & Insights
            </button>
          </div>
        </div>
      </div>

      <p className="wsr-status-msg">{message}</p>
      {busy ? (
        <ol className="wsr-stages">
          {GENERATE_STAGES.map((label, index) => (
            <li key={label} className={index <= stage ? "active" : ""}>
              {label}
            </li>
          ))}
        </ol>
      ) : null}
      {job?.status === "failed" ? (
        <button type="button" className="btn btn-outline" onClick={() => void retry()} disabled={busy}>
          Retry generation
        </button>
      ) : null}

      {report ? (
        <div className="dashboard">
          <section className="wsr-hero">
            <div className="hero-identity">
              <h3>
                <span className="material-symbols-outlined" aria-hidden="true">
                  account_balance
                </span>
                {unavailable(facts.project_name)}
              </h3>
              <p className="hero-publish">WSR Publish Date: {shortDate(report.as_of_date)}</p>
            </div>
            <div className="hero-countdown">
              <p className="metric-label">Countdown</p>
              <p className={`countdown-value ${facts.countdown_days != null ? "tone-bad" : ""}`}>
                {facts.countdown_days != null ? facts.countdown_days : "Unavailable"}
                {facts.countdown_days != null ? <span>Days</span> : null}
              </p>
              <p className="metric-hint">to Go-Live</p>
            </div>
            <div className="hero-progress">
              <WsrProgressRing value={facts.overall_progress} />
              <div>
                <p className="metric-label">Overall Progress</p>
                <p className="metric-hint">By work completion</p>
              </div>
            </div>
          </section>

          <div className="kpi-grid">
            {kpis.map((kpi, index) => (
              <KpiCard
                key={kpi.label}
                label={kpi.label}
                value={kpi.value}
                hint={kpi.hint}
                icon={KPI_ICONS[index]}
                tone={KPI_TONES[index]}
              />
            ))}
          </div>

          <Section n={1} title="AI Executive Summary" flush>
            <ExecutiveSummaryPanel
              health={facts.project_health}
              summary={facts.executive_summary}
              overview={facts.executive_overview}
            />
          </Section>

          <Section
            n={2}
            title="Project Timeline"
            hint="Phases from project planning to Go-Live. The dashed marker shows today's position; hover any bar for full dates."
          >
            {facts.timeline?.length ? (
              <WsrGantt phases={facts.timeline} asOf={report.as_of_date} />
            ) : (
              <p>A timeline cannot be generated</p>
            )}
          </Section>

          <Section n={3} title="Phase-Wise Status">
            {facts.phase_statuses?.length ? (
              <table className="phase-table">
                <thead>
                  <tr>
                    <th>WBS</th>
                    <th>Phase</th>
                    <th>Planned Window</th>
                    <th>Deviated Window</th>
                    <th>Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {facts.phase_statuses.map((phase: PhaseStatus, index) => {
                    const active = phase.state !== "not_started";
                    const hasActual = Boolean(phase.actual_start || phase.actual_finish);
                    return (
                      <tr key={`${phase.name}-${index}`} className={active ? "phase-active" : undefined}>
                        <td className="mono">{phaseWbs(phase, index)}</td>
                        <td>
                          {phase.name}
                          {phase.state === "in_progress" ? (
                            <span className="status-badge">In Progress</span>
                          ) : null}
                        </td>
                        <td className="mono">
                          {windowRange(phase.planned_start, phase.planned_finish)}
                        </td>
                        <td className={`mono${hasActual ? " phase-deviated" : ""}`}>
                          {hasActual
                            ? windowRange(phase.actual_start, phase.actual_finish)
                            : "—"}
                        </td>
                        <td>
                          {phase.state === "not_started" && !phase.progress ? (
                            <div className="phase-progress muted">
                              <div className="phase-bar state-not_started" />
                              <span>Not started</span>
                            </div>
                          ) : (
                            <div className="phase-progress">
                              <div className={`phase-bar state-${phase.state}`}>
                                <span
                                  style={{
                                    width: `${Math.min(100, Math.max(0, phase.progress ?? 0))}%`,
                                  }}
                                />
                              </div>
                              <strong>
                                {phase.progress == null ? phaseState(phase.state) : percent(phase.progress)}
                              </strong>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p>Unavailable</p>
            )}
          </Section>

          <div className="wsr-paired">
            <Section n={4} title="Progress to Date">
              {facts.progress_to_date?.length ? (
                <table className="milestone-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Start</th>
                      <th>End</th>
                      <th>Complete</th>
                    </tr>
                  </thead>
                  <tbody>
                    {facts.progress_to_date.map((item: ProgressItem, index) => (
                      <tr key={`${item.name}-${index}`}>
                        <td>{item.name}</td>
                        <td className="mono">{shortDate(item.scheduled_start)}</td>
                        <td className="mono">{shortDate(item.scheduled_finish || item.date)}</td>
                        <td>{item.progress == null ? "Unavailable" : percent(item.progress)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>No tasks scheduled in the current week</p>
              )}
            </Section>

            <Section
              n={5}
              title="Upcoming Milestones"
              hint="Key dates from today through the next planned tasks."
            >
              {facts.upcoming_milestones?.length ? (
                <table className="milestone-table">
                  <thead>
                    <tr>
                      <th>Start</th>
                      <th>End</th>
                      <th>Milestone / Activity</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {facts.upcoming_milestones.map((item: MilestoneItem, index) => {
                      const today = isSameDay(
                        item.scheduled_start || item.date,
                        report.as_of_date,
                      );
                      return (
                        <tr key={`${item.name}-${index}`} className={today ? "milestone-today" : undefined}>
                          <td className="mono">{shortDate(item.scheduled_start).replace(/ \d{4}$/, "")}</td>
                          <td className="mono">
                            {shortDate(item.scheduled_finish || item.date).replace(/ \d{4}$/, "")}
                          </td>
                          <td>{item.name}</td>
                          <td>{today ? <span className="today-badge">Today</span> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <p>No upcoming planned tasks</p>
              )}
            </Section>
          </div>

          <Section n={6} title="Risks & Focus Areas">
            <InsightCards
              items={visibleInsights(report.risks)}
              tone="risk"
              empty="No items identified from the plan"
            />
          </Section>
        </div>
      ) : busy ? null : (
        <div className="wsr-empty">
          <h3>No report yet</h3>
          <p>Upload a Microsoft Project (.mpp) file, then generate WSR & Insights to open the dashboard.</p>
        </div>
      )}
    </section>
  );
}

function ExecutiveSummaryPanel({
  health,
  summary,
  overview,
}: {
  health?: string | null;
  summary?: ExecutiveSummary | null;
  overview?: string | null;
}) {
  const tone =
    health && ["on_track", "at_risk", "off_track", "unavailable"].includes(health)
      ? health
      : "unavailable";
  if (!summary) {
    return <p className="overview-copy">{unavailable(overview)}</p>;
  }
  return (
    <div className="exec-summary">
      <p className="exec-health">
        Overall Health:{" "}
        <span className={`health health-${tone}`}>{healthLabel(health).toUpperCase()}</span>
      </p>
      <p className="overview-copy">{unavailable(summary.summary)}</p>
      <ExecBlock title="Key Highlights" empty="Unavailable from plan data">
        {summary.highlights.map((item, index) => (
          <li key={`${item.title}-${index}`}>
            <strong>{item.title}:</strong> {item.description}
          </li>
        ))}
      </ExecBlock>
      <ExecBlock title="Current Focus" empty="Unavailable from plan data">
        {summary.current_focus.map((item, index) => (
          <li key={`${item.title}-${index}`}>
            <strong>{item.title}</strong>
            {item.description ? ` — ${item.description}` : ""}
          </li>
        ))}
      </ExecBlock>
      <ExecBlock title="Executive Risks" empty="Unavailable from plan data">
        {summary.executive_risks.map((item, index) => (
          <li key={`${item.title}-${index}`}>
            <span className={`exec-severity exec-severity-${item.severity}`}>{item.severity}</span>{" "}
            <strong>{item.title}:</strong> {item.description}
          </li>
        ))}
      </ExecBlock>
      <ExecBlock title="AI Recommended Actions" empty="Unavailable from plan data">
        {summary.recommended_actions.map((item, index) => (
          <li key={`${item.action}-${index}`}>
            <span className="exec-ai-label">AI Recommended Action</span> {item.action}
            {item.reason ? ` (${item.reason})` : ""}
          </li>
        ))}
      </ExecBlock>
    </div>
  );
}

function ExecBlock({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: ReactNode;
}) {
  const items = Array.isArray(children) ? children : [children];
  const present = items.filter(Boolean);
  return (
    <div className="exec-block">
      <h4>{title}</h4>
      {present.length ? <ul>{children}</ul> : <p className="muted">{empty}</p>}
    </div>
  );
}

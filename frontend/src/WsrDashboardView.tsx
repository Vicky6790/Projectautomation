import { useContext, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { generateWsr, getWsrRequest, retryJob } from "./api";
import { DelayMappingPanel } from "./components/DelayMappingPanel";
import { FileUploader } from "./components/FileUploader";
import { WsrGantt } from "./components/WsrGantt";
import { WsrProgressRing } from "./components/WsrProgressRing";
import { ShellMetaContext } from "./shellMeta";
import type {
  AiDerivedItem,
  FileRecord,
  MilestoneItem,
  PhaseStatus,
  ProcessingResponse,
  ProgressItem,
  WsrPlanFacts,
} from "./types";
import {
  personDaysLabel,
  percent,
  phaseState,
  phaseWbs,
  shortDate,
  splitInsight,
  unavailable,
  weekDate,
} from "./wsrFormat";
import {
  asWsrReport,
  clearWsrSession,
  readWsrSession,
  restoredUpload,
  saveWsrSession,
} from "./wsrSession";

const GENERATE_STAGES = [
  "Reading the file",
  "Extracting plan values",
  "Creating narrative",
  "Rendering the report",
];

const KPI_TONES = ["kpi-indigo", "kpi-emerald", "kpi-amber", "kpi-blue"] as const;
const KPI_ICONS = ["calendar_today", "person_add", "schedule", "assignment"] as const;

function asReport(result: ProcessingResponse["result"]) {
  return asWsrReport(result);
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
  action,
  children,
  flush,
}: {
  n: number;
  title: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className={`wsr-section${flush ? " wsr-section-flush" : ""}`}>
      <div className="wsr-section-head">
        <div className="wsr-section-title-row">
          <h3>
            <span className="wsr-num">{n}</span>
            {title}
          </h3>
          {action}
        </div>
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
  const navigate = useNavigate();
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [message, setMessage] = useState(
    "Upload a Microsoft Project (.mpp) file, then generate WSR & Insights.",
  );

  useEffect(() => {
    const session = readWsrSession();
    if (!session) {
      return;
    }
    setUploaded(restoredUpload(session));
    getWsrRequest(session.handle)
      .then((result) => {
        setJob(result);
        if (result.status === "succeeded") {
          setMessage("Status report ready.");
        }
      })
      .catch(() => {
        clearWsrSession();
      });
  }, []);

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
      if (result.status === "succeeded") {
        saveWsrSession(handle, uploaded?.filename || "plan.mpp");
        setMessage("Status report ready.");
      } else {
        setMessage("Generation failed.");
      }
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
                  clearWsrSession();
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
                clearWsrSession();
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

          <Section n={1} title="Executive Summary" flush>
            <p className="overview-copy">
              {unavailable(facts.executive_summary?.summary || facts.executive_overview)}
            </p>
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

          <Section
            n={3}
            title="Phase-Wise Status"
            action={
              <button
                type="button"
                className="btn btn-outline delay-mapping-cta"
                disabled={!report}
                onClick={() => navigate("/wsr/delay-mapping")}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  table_view
                </span>
                Go-Live Delay Mapping
              </button>
            }
          >
            {facts.phase_statuses?.length ? (
              <table className="phase-table">
                <thead>
                  <tr>
                    <th>WBS</th>
                    <th>Phases</th>
                    <th>Start Date</th>
                    <th>Planned End</th>
                    <th>Deviated Date</th>
                    <th>Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {facts.phase_statuses.map((phase: PhaseStatus, index) => {
                    const active = phase.state !== "not_started";
                    const startDate = shortDate(phase.planned_start || phase.actual_start);
                    const plannedEnd = shortDate(phase.planned_finish);
                    const currentFinish = shortDate(phase.actual_finish);
                    const hasDeviation =
                      Boolean(phase.actual_finish) && plannedEnd !== currentFinish;
                    return (
                      <tr key={`${phase.name}-${index}`} className={active ? "phase-active" : undefined}>
                        <td className="mono">{phaseWbs(phase, index)}</td>
                        <td>
                          {phase.name}
                          {phase.state === "in_progress" ? (
                            <span className="status-badge">In Progress</span>
                          ) : null}
                        </td>
                        <td className="mono">{startDate}</td>
                        <td className="mono">{plannedEnd}</td>
                        <td className={`mono${hasDeviation ? " phase-deviated" : ""}`}>
                          {hasDeviation ? currentFinish : "—"}
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

          <Section
            n={4}
            title="Go-Live Delay Mapping"
            hint="Working-calendar Go-Live shift, attributed from Delay and Additional tasks on the Go-Live path. AI does not calculate these days."
            action={
              <button
                type="button"
                className="btn btn-outline delay-mapping-cta"
                disabled={!report}
                onClick={() => navigate("/wsr/delay-mapping")}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  open_in_new
                </span>
                Open full sheet
              </button>
            }
          >
            <DelayMappingPanel mapping={facts.delay_mapping ?? {}} asOf={facts.as_of_date} />
          </Section>

          <div className="wsr-paired">
            <Section n={5} title="Progress of current week">
              {facts.progress_to_date?.length ? (
                <table className="milestone-table">
                  <thead>
                    <tr>
                      <th>Tasks</th>
                      <th>Start Date</th>
                      <th>End Date</th>
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
              n={6}
              title="Upcoming Milestones Of Next Week"
              hint="Incomplete work overlapping the calendar week after the as-of week."
            >
              {facts.upcoming_milestones?.length ? (
                <table className="milestone-table">
                  <thead>
                    <tr>
                      <th>Start Date</th>
                      <th>End Date</th>
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
                          <td className="mono">{weekDate(item.scheduled_start)}</td>
                          <td className="mono">{weekDate(item.scheduled_finish || item.date)}</td>
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

          <Section n={7} title="Risks & Focus Areas">
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

import { useContext, useEffect, useState, type ReactNode } from "react";
import { generateWsr, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ModuleHero, ModuleLanding } from "./components/ModuleHero";
import { WsrGantt } from "./components/WsrGantt";
import { WsrProgressRing } from "./components/WsrProgressRing";
import { PrintViewBar } from "./components/PrintViewBar";
import { downloadLandscapePdf } from "./printPage";
import { ShellMetaContext } from "./shellMeta";
import type {
  AiDerivedItem,
  FileRecord,
  MilestoneItem,
  PhaseStatus,
  ProcessingResponse,
  ProgressItem,
  ProjectWsrDashboard,
  WsrPlanFacts,
} from "./types";
import {
  asPercent,
  personDaysLabel,
  percent,
  phaseState,
  phaseWbs,
  currentWeekRange,
  upcomingWeekRange,
  shortDate,
  splitInsight,
  unavailable,
  weekDate,
} from "./wsrFormat";
import {
  asWsrReport,
  clearWsrSession,
  saveWsrSession,
  WSR_RESET_EVENT,
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

function WsrProjectBoard({
  board,
  asOf,
  active,
  sharedProgramMetrics,
  variant = "wsr",
}: {
  board: ProjectWsrDashboard;
  asOf?: string | null;
  active: boolean;
  sharedProgramMetrics?: boolean;
  variant?: "wsr" | "executive";
}) {
  const facts = board.facts;
  const executive = variant === "executive";
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
  let section = 1;
  return (
    <div className={active ? "dashboard wsr-project-pane is-active" : "dashboard wsr-project-pane"}>
      <WsrHero
        name={facts.project_name}
        asOf={asOf}
        countdownDays={sharedProgramMetrics ? null : facts.countdown_days}
        overallProgress={facts.overall_progress}
        hideCountdown={Boolean(sharedProgramMetrics)}
        progressHint={sharedProgramMetrics ? "This project" : "By work completion"}
      />

      {executive ? null : (
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
      )}

      {executive ? null : (
        <Section n={section++} title="Executive Summary" flush>
          <OverviewCopy text={facts.executive_summary?.summary || facts.executive_overview} />
        </Section>
      )}

      <Section
        n={section++}
        title="Project Timeline"
        hint="Phases from project planning to Go-Live. The dashed marker shows today's position."
      >
        {facts.timeline?.length ? (
          <WsrGantt
            phases={facts.timeline}
            asOf={asOf}
            endMode={executive ? "deviated" : "planned"}
            showProgress={executive}
          />
        ) : (
          <p>A timeline cannot be generated</p>
        )}
      </Section>

      {executive ? null : (
      <Section n={section++} title="Phase-Wise Status">
        {facts.phase_statuses?.length ? (
          <table className="phase-table">
            <thead>
              <tr>
                <th>WBS</th>
                <th>Phases</th>
                <th>Baseline Start Date</th>
                <th>Baseline End Date</th>
                <th>Deviated End Date</th>
                <th>Progress</th>
              </tr>
            </thead>
            <tbody>
              {facts.phase_statuses.map((phase: PhaseStatus, index) => {
                const inFlight = phase.state !== "not_started";
                const startDate = shortDate(phase.planned_start || phase.actual_start);
                const plannedEnd = shortDate(phase.planned_finish);
                const currentFinish = shortDate(phase.actual_finish);
                const hasDeviation = Boolean(phase.actual_finish) && plannedEnd !== currentFinish;
                return (
                  <tr key={`${phase.name}-${index}`} className={inFlight ? "phase-active" : undefined}>
                    <td className="mono">{phaseWbs(phase, index)}</td>
                    <td>
                      {phase.name}
                      {phase.state === "in_progress" ? <span className="status-badge">In Progress</span> : null}
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
                            <span style={{ width: `${Math.min(100, Math.max(0, asPercent(phase.progress ?? 0)))}%` }} />
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
      )}

      {executive ? null : (
      <div className="wsr-paired">
        <Section
          n={section++}
          title="Progress of current week"
          hint={`Current Week: ${currentWeekRange(asOf, facts.current_week_start, facts.current_week_end)}`}
        >
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
                    <td className="task-hierarchy">{item.label || item.name}</td>
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
          n={section++}
          title="Upcoming Milestones"
          hint={`Upcoming 7 Days: ${upcomingWeekRange(asOf, facts.upcoming_start, facts.upcoming_end)}`}
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
                  const today = isSameDay(item.scheduled_start || item.date, asOf);
                  return (
                    <tr key={`${item.name}-${index}`} className={today ? "milestone-today" : undefined}>
                      <td className="mono">{weekDate(item.scheduled_start)}</td>
                      <td className="mono">{weekDate(item.scheduled_finish || item.date)}</td>
                      <td className="task-hierarchy">{item.label || item.name}</td>
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
      )}

      {executive ? null : (
      <Section n={section++} title="Risks & Focus Areas">
        <InsightCards
          items={visibleInsights(board.risks)}
          tone="risk"
          empty="No material risks identified in the current phase."
        />
      </Section>
      )}
    </div>
  );
}

function WsrHero({
  name,
  asOf,
  countdownDays,
  overallProgress,
  hideCountdown,
  progressHint,
}: {
  name?: string | null;
  asOf?: string | null;
  countdownDays?: number | null;
  overallProgress?: number | null;
  hideCountdown?: boolean;
  progressHint?: string;
}) {
  return (
    <section className={`wsr-hero${hideCountdown ? " wsr-hero-no-countdown" : ""}`}>
      <div className="hero-identity">
        <h3>
          <span className="material-symbols-outlined" aria-hidden="true">
            account_balance
          </span>
          {unavailable(name)}
        </h3>
        <p className="hero-publish">Report Date: {shortDate(asOf)}</p>
      </div>
      {hideCountdown ? null : (
        <div className="hero-countdown">
          <p className="metric-label">Countdown</p>
          <p className={`countdown-value ${countdownDays != null ? "countdown-ochre" : ""}`}>
            {countdownDays != null ? countdownDays : "Unavailable"}
            {countdownDays != null ? <span>Days</span> : null}
          </p>
          <p className="metric-hint">to Go-Live</p>
        </div>
      )}
      <div className="hero-progress">
        <WsrProgressRing value={overallProgress} />
        <div>
          <p className="metric-label">Overall Progress</p>
          <p className="metric-hint">{progressHint || "By work completion"}</p>
        </div>
      </div>
    </section>
  );
}

function OverviewCopy({ text }: { text?: string | null }) {
  const paras = (text || "")
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!paras.length) {
    return (
      <div className="overview-copy">
        <p>Unavailable</p>
      </div>
    );
  }
  return (
    <div className="overview-copy">
      {paras.map((part, index) => (
        <p key={index}>{part}</p>
      ))}
    </div>
  );
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
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [message, setMessage] = useState(
    "Upload a Microsoft Project (.mpp) file, then generate WSR & Insights.",
  );

  const [activeCode, setActiveCode] = useState<string | null>(null);
  const [reportKind, setReportKind] = useState<"wsr" | "executive">("wsr");
  const [printView, setPrintView] = useState(false);
  const [savingPdf, setSavingPdf] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("pa-print-view", printView);
    return () => document.documentElement.classList.remove("pa-print-view");
  }, [printView]);

  useEffect(() => {
    const reset = () => {
      setUploaded(null);
      setJob(null);
      setBusy(false);
      setStage(0);
      setActiveCode(null);
      setReportKind("wsr");
      setPrintView(false);
      setMessage("Upload a Microsoft Project (.mpp) file, then generate WSR & Insights.");
    };
    window.addEventListener(WSR_RESET_EVENT, reset);
    return () => window.removeEventListener(WSR_RESET_EVENT, reset);
  }, []);

  const report = asReport(job?.result ?? null);
  const boards = report?.projects ?? [];
  const activeBoard = boards.find((board) => board.project_code === activeCode) ?? boards[0];
  const facts: WsrPlanFacts = activeBoard?.facts ?? report?.facts ?? {};

  useEffect(() => {
    if (!boards.length) {
      setActiveCode(null);
      return;
    }
    if (!boards.some((board) => board.project_code === activeCode)) {
      setActiveCode(boards[0].project_code);
    }
  }, [activeCode, boards]);

  useEffect(() => {
    const identity = [report?.portfolio_name, facts.project_name, facts.project_owner]
      .filter(Boolean)
      .join(" · ");
    setPageMeta(identity);
    return () => setPageMeta("");
  }, [facts.project_name, facts.project_owner, report?.portfolio_name, setPageMeta]);

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

  async function runGenerate(handle: string, kind: "wsr" | "executive" = "wsr") {
    setReportKind(kind);
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
    await runGenerate(uploaded.id, reportKind);
  }

  async function printForMeeting() {
    if (!report) {
      return;
    }
    setSavingPdf(true);
    try {
      await downloadLandscapePdf(
        ".wsr-report",
        reportKind === "executive" ? "Executive Summary.pdf" : "WSR Report.pdf",
      );
    } catch {
      setMessage("Could not save the PDF.");
    } finally {
      setSavingPdf(false);
    }
  }

  return (
    <section className="wsr-page">
      <ModuleHero
        tone="wsr"
        icon="insights"
        kicker="WSR & Insights"
        title="Weekly status from the live plan"
        subtitle="Upload the current MPP. Go-Live, progress, timeline, and insights come from the plan — missing values stay Unavailable."
      />

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
                  setActiveCode(null);
                  setReportKind("wsr");
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
                setActiveCode(null);
                setReportKind("wsr");
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
              onClick={() => setPrintView(true)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                download
              </span>
              Download to PDF
            </button>
            <button
              type="button"
              className={report && reportKind === "executive" ? "btn btn-primary" : "btn btn-outline"}
              disabled={!uploaded || busy}
              onClick={() => uploaded && void runGenerate(uploaded.id, "executive")}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                summarize
              </span>
              Generate Executive Summary
            </button>
            <button
              type="button"
              className={report && reportKind === "executive" ? "btn btn-outline" : "btn btn-primary"}
              disabled={!uploaded || busy}
              onClick={() => uploaded && void runGenerate(uploaded.id, "wsr")}
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
        <>
          {printView ? (
            <PrintViewBar
              saving={savingPdf}
              onSave={() => void printForMeeting()}
              onExit={() => setPrintView(false)}
            />
          ) : null}
        <div className="wsr-report">
          {report.portfolio ? (
            <WsrHero
              name={report.portfolio.name}
              asOf={report.as_of_date}
              countdownDays={report.portfolio.countdown_days}
              overallProgress={report.portfolio.overall_progress}
              progressHint="All projects"
            />
          ) : null}
          {boards.length > 1 ? (
            <div className="wsr-project-tabs" role="tablist" aria-label="Projects">
              {boards.map((board) => (
                <button
                  key={board.project_code}
                  type="button"
                  role="tab"
                  aria-selected={board.project_code === activeBoard?.project_code}
                  className={
                    board.project_code === activeBoard?.project_code
                      ? "wsr-project-tab is-active"
                      : "wsr-project-tab"
                  }
                  onClick={() => setActiveCode(board.project_code)}
                >
                  {board.project_name || `Project ${board.project_code}`}
                </button>
              ))}
            </div>
          ) : null}
          {boards.map((board) => (
            <WsrProjectBoard
              key={board.project_code}
              board={board}
              asOf={report.as_of_date}
              active={board.project_code === activeBoard?.project_code}
              sharedProgramMetrics={Boolean(report.portfolio)}
              variant={reportKind}
            />
          ))}
        </div>
        </>
      ) : busy ? null : (
        <ModuleLanding
          tone="wsr"
          steps={[
            { icon: "upload_file", title: "Upload the MPP", copy: "Microsoft Project is the single source for dates, work, and Go-Live." },
            { icon: "insights", title: "Generate the WSR", copy: "Plan facts, phase status, and this week’s work are assembled for the meeting." },
            { icon: "summarize", title: "Or generate an Executive Summary", copy: "The same plan, with a timeline that uses Deviated End Date plus phase progress." },
            { icon: "picture_as_pdf", title: "Share the dashboard", copy: "Download to PDF when the report is ready for the weekly review." },
          ]}
        />
      )}
    </section>
  );
}

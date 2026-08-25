import { useState } from "react";
import { downloadWsrReport, generateWsr, getWsrEvidence, reviewWsrItem, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import { WsrEvidencePanel } from "./components/WsrEvidencePanel";
import { WsrInsightItem } from "./components/WsrInsightItem";
import type {
  AiDerivedItem,
  FileRecord,
  MilestoneItem,
  PhaseStatus,
  ProcessingResponse,
  ProgressItem,
  StatusReport,
  WsrEvidenceResponse,
  WsrPlanFacts,
} from "./types";
import {
  healthLabel,
  namedDate,
  percent,
  phaseState,
  unavailable,
} from "./wsrFormat";

const AI_SECTIONS: { key: keyof StatusReport; label: string }[] = [
  { key: "client_needs", label: "What We Need From the Bank Team" },
  { key: "issues", label: "Issues" },
  { key: "dependencies", label: "Dependencies" },
  { key: "risks", label: "Risks & Focus Areas" },
  { key: "management_attention", label: "Management Attention" },
  { key: "decisions_required", label: "Decisions Required" },
  { key: "next_7_day_priorities", label: "Next Seven-Day Priorities" },
];

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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </div>
  );
}

export function WsrDashboardView() {
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(
    "Upload a Microsoft Project (.mpp) file to generate WSR & Insights.",
  );
  const [evidence, setEvidence] = useState<WsrEvidenceResponse | null>(null);

  const report = asReport(job?.result ?? null);
  const facts: WsrPlanFacts = report?.facts ?? {};
  const pendingReview = Boolean(report && !report.exportable && job?.status === "succeeded");

  async function runGenerate(handle: string) {
    setBusy(true);
    setEvidence(null);
    setMessage("Generating the status report…");
    try {
      const result = await generateWsr(handle);
      setJob(result);
      setMessage(
        result.status === "succeeded"
          ? result.result && (result.result as StatusReport).exportable
            ? "Status report ready."
            : "Status report ready. Review each AI-derived item before downloading the PDF."
          : "Generation failed.",
      );
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

  async function download() {
    if (!uploaded) {
      return;
    }
    try {
      const { blob, filename } = await downloadWsrReport(uploaded.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Download failed");
    }
  }

  async function review(
    item: AiDerivedItem,
    decision: "kept" | "edited" | "removed",
    content?: string,
  ) {
    if (!uploaded) {
      return;
    }
    setBusy(true);
    try {
      const updated = await reviewWsrItem(uploaded.id, item.id, { decision, content });
      setJob(updated);
      const ready = Boolean((updated.result as StatusReport | null)?.exportable);
      setMessage(
        ready
          ? "All insights reviewed. The PDF can be downloaded."
          : "Insight updated. Continue reviewing remaining items.",
      );
      if (evidence?.item_id === item.id) {
        setEvidence(null);
      }
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  async function viewSource(item: AiDerivedItem) {
    if (!uploaded) {
      return;
    }
    try {
      setEvidence(await getWsrEvidence(uploaded.id, item.id));
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Source details failed");
    }
  }

  return (
    <section className="panel wsr">
      <h2>WSR & Insights</h2>
      <p>{message}</p>
      <FileUploader
        disabled={busy}
        accept=".mpp,application/vnd.ms-project"
        label="Choose Microsoft Project file (.mpp)"
        endpoint="/api/v1/wsr/uploads"
        onUploaded={(file) => {
          setUploaded(file);
          setJob(null);
          void runGenerate(file.id);
        }}
        onError={setMessage}
      />
      {uploaded ? (
        <div className="actions">
          <p>File: {uploaded.filename}</p>
          <button type="button" onClick={() => void runGenerate(uploaded.id)} disabled={busy}>
            Generate report
          </button>
        </div>
      ) : null}
      {busy ? <p className="processing">Processing…</p> : null}
      {job?.status === "failed" ? (
        <button type="button" onClick={() => void retry()} disabled={busy}>
          Retry generation
        </button>
      ) : null}
      <ReportDownloadControl
        enabled={Boolean(report?.exportable) && job?.status === "succeeded" && !busy}
        label="Download PDF"
        onDownload={() => void download()}
      />
      {pendingReview ? <p>Review is required before the report can be downloaded.</p> : null}

      {report ? (
        <div className="dashboard">
          <header className="wsr-identity">
            <div>
              <h3>{unavailable(facts.project_name)}</h3>
              <p className="muted">
                Owner: {unavailable(facts.project_owner)} · as of {unavailable(report.as_of_date)} ·
                generated {unavailable(report.generated_at)}
                {report.planned_only ? " · planned data only" : ""}
              </p>
            </div>
            <p className={`health health-${report.project_health ?? "unavailable"}`}>
              Project health: {healthLabel(report.project_health)}
            </p>
          </header>

          <section>
            <h3>Project summary</h3>
            <div className="metric-grid">
              <Metric label="Overall Progress" value={percent(facts.overall_progress)} />
              <Metric
                label="Last Signed-Off Milestone"
                value={namedDate(facts.last_signed_off_milestone)}
              />
              <Metric label="Work Items Completed" value={unavailable(facts.completed_work_items)} />
              <Metric label="Team Capacity" value={percent(facts.capacity_utilization)} />
              <Metric label="Next Gate" value={namedDate(facts.next_gate)} />
              <Metric label="Go-Live" value={unavailable(facts.planned_go_live_date)} />
            </div>
          </section>

          <section>
            <h3>Executive Overview</h3>
            <div className="metric-grid">
              <Metric label="Overall Progress" value={percent(facts.overall_progress)} />
              <Metric label="Phases to Go-Live" value={unavailable(facts.phase_count)} />
              <Metric label="People Planned" value={unavailable(facts.people_planned)} />
              <Metric label="Resources Deployed" value={unavailable(facts.resources_deployed)} />
              <Metric label="Days to Go-Live" value={unavailable(facts.countdown_days)} />
            </div>
            <p>{unavailable(facts.executive_overview)}</p>
          </section>

          <section>
            <h3>Project Timeline</h3>
            {facts.timeline?.length ? (
              <ul>
                {facts.timeline.map((phase: PhaseStatus) => (
                  <li key={phase.name}>
                    {phase.name}: {unavailable(phase.planned_start)} – {unavailable(phase.planned_finish)}
                  </li>
                ))}
              </ul>
            ) : (
              <p>A timeline cannot be generated</p>
            )}
          </section>

          <section>
            <h3>Phase-Wise Status</h3>
            {facts.phase_statuses?.length ? (
              <ul>
                {facts.phase_statuses.map((phase: PhaseStatus) => (
                  <li key={phase.name}>
                    {phase.name}: {phaseState(phase.state)} ({unavailable(phase.planned_start)} –{" "}
                    {unavailable(phase.planned_finish)}, {percent(phase.progress)})
                  </li>
                ))}
              </ul>
            ) : (
              <p>Unavailable</p>
            )}
          </section>

          <section>
            <h3>Progress to Date</h3>
            {facts.progress_to_date?.length ? (
              <ul>
                {facts.progress_to_date.map((item: ProgressItem, index) => (
                  <li key={`${item.name}-${index}`}>
                    {item.name}: {unavailable(item.date)} ({percent(item.progress)})
                  </li>
                ))}
              </ul>
            ) : (
              <p>Unavailable</p>
            )}
          </section>

          <section>
            <h3>Upcoming Milestones</h3>
            {facts.upcoming_milestones?.length ? (
              <ul>
                {facts.upcoming_milestones.map((item: MilestoneItem, index) => (
                  <li key={`${item.name}-${index}`}>
                    {item.name}: {unavailable(item.date)}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No upcoming milestone was identified</p>
            )}
          </section>

          {AI_SECTIONS.map((section) => {
            const items = visibleInsights((report[section.key] as AiDerivedItem[]) ?? []);
            return (
              <section key={section.key}>
                <h3>{section.label}</h3>
                {items.length === 0 ? (
                  <p>No items identified from the plan</p>
                ) : (
                  <ul className="insight-list">
                    {items.map((item) => (
                      <WsrInsightItem
                        key={item.id}
                        item={item}
                        disabled={busy}
                        onReview={review}
                        onViewSource={(selected) => void viewSource(selected)}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      ) : null}

      {evidence ? <WsrEvidencePanel evidence={evidence} onClose={() => setEvidence(null)} /> : null}
    </section>
  );
}

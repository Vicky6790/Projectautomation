import { useMemo, useState } from "react";
import { downloadWsrReport, generateWsr, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import type { AiDerivedItem, FileRecord, ProcessingResponse, StatusReport } from "./types";

type ListKey =
  | "progress"
  | "milestones"
  | "client_needs"
  | "risks"
  | "issues"
  | "dependencies"
  | "management_attention"
  | "decisions_required"
  | "next_7_day_priorities";

const SECTIONS: { key: ListKey; label: string }[] = [
  { key: "progress", label: "Progress to Date" },
  { key: "milestones", label: "Upcoming Milestones" },
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

function rows(value: string[] | AiDerivedItem[]): { key: string; text: string }[] {
  return value.map((item, index) => {
    if (typeof item === "string") {
      return { key: `${item}-${index}`, text: item };
    }
    return { key: item.id || String(index), text: item.content };
  });
}

function healthLabel(value: string | null | undefined): string {
  if (value === "on_track") {
    return "On track";
  }
  if (value === "at_risk") {
    return "At risk";
  }
  if (value === "off_track") {
    return "Off track";
  }
  if (value === "unavailable") {
    return "Unavailable — insufficient plan data";
  }
  return value || "Unavailable";
}

export function WsrDashboardView() {
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Upload a Microsoft Project (.mpp) file to generate WSR & Insights.");
  const [selected, setSelected] = useState<ListKey>("progress");

  const report = asReport(job?.result ?? null);
  const counts = useMemo(() => {
    if (!report) {
      return {};
    }
    return Object.fromEntries(
      SECTIONS.map((section) => [section.key, report[section.key].length]),
    ) as Record<string, number>;
  }, [report]);

  async function runGenerate(handle: string) {
    setBusy(true);
    setMessage("Generating the status report…");
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

  async function download() {
    if (!uploaded) {
      return;
    }
    try {
      const blob = await downloadWsrReport(uploaded.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "wsr-report.md";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Download failed");
    }
  }

  const selectedRows = report ? rows(report[selected]) : [];

  return (
    <section className="panel">
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
      {uploaded ? <p>File: {uploaded.filename}</p> : null}
      {busy ? <p className="processing">Processing…</p> : null}
      {job?.status === "failed" ? (
        <button type="button" onClick={() => void retry()} disabled={busy}>
          Retry generation
        </button>
      ) : null}
      <ReportDownloadControl
        enabled={Boolean(report?.exportable) && job?.status === "succeeded" && !busy}
        onDownload={() => void download()}
      />
      {report && !report.exportable && job?.status === "succeeded" ? (
        <p>Review is required before the report can be downloaded.</p>
      ) : null}
      {report ? (
        <div className="dashboard">
          <p className={`health health-${report.project_health ?? "unavailable"}`}>
            Project health: {healthLabel(report.project_health)}
          </p>
          <p className="muted">
            {report.facts?.project_name ?? "Project"}
            {report.facts?.project_owner ? ` · ${report.facts.project_owner}` : ""}
            {` · as of ${report.as_of_date ?? "today"}`}
            {report.generated_at ? ` · generated ${report.generated_at}` : ""}
            {report.planned_only ? " · planned data only" : ""}
          </p>
          {report.facts?.executive_overview ? <p>{report.facts.executive_overview}</p> : null}
          <div className="findings">
            <ul className="categories">
              {SECTIONS.map((section) => (
                <li key={section.key}>
                  <button
                    type="button"
                    className={selected === section.key ? "active" : ""}
                    onClick={() => setSelected(section.key)}
                  >
                    {section.label} ({counts[section.key] ?? 0})
                  </button>
                </li>
              ))}
            </ul>
            <div className="category-detail">
              <h3>{SECTIONS.find((section) => section.key === selected)?.label}</h3>
              {selectedRows.length === 0 ? (
                <p>No items identified from the plan</p>
              ) : (
                <ul>
                  {selectedRows.map((item) => (
                    <li key={item.key}>{item.text}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

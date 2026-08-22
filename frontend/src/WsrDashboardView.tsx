import { useMemo, useState } from "react";
import { downloadWsrReport, generateWsr, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import type { FileRecord, ProcessingResponse, StatusReport } from "./types";

type SectionKey = Exclude<
  keyof StatusReport,
  "request_handle" | "as_of_date" | "planned_only" | "project_health"
>;

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: "progress", label: "Progress" },
  { key: "milestones", label: "Milestones" },
  { key: "risks", label: "Risks" },
  { key: "issues", label: "Issues" },
  { key: "dependencies", label: "Dependencies" },
  { key: "management_attention", label: "Management attention" },
  { key: "decisions_required", label: "Decisions required" },
  { key: "next_7_day_priorities", label: "Next 7-day priorities" },
];

function asReport(result: ProcessingResponse["result"]): StatusReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as StatusReport;
  return {
    as_of_date: data.as_of_date ?? null,
    planned_only: Boolean(data.planned_only),
    project_health: data.project_health ?? null,
    progress: data.progress ?? [],
    milestones: data.milestones ?? [],
    risks: data.risks ?? [],
    issues: data.issues ?? [],
    dependencies: data.dependencies ?? [],
    management_attention: data.management_attention ?? [],
    decisions_required: data.decisions_required ?? [],
    next_7_day_priorities: data.next_7_day_priorities ?? [],
  };
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
  return value || "Unknown";
}

export function WsrDashboardView() {
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Upload a Microsoft Project (.mpp) file to generate a weekly status report.");
  const [selected, setSelected] = useState<SectionKey>("progress");

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

  return (
    <section className="panel">
      <h2>Weekly Status Report</h2>
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
      <ReportDownloadControl enabled={job?.status === "succeeded" && !busy} onDownload={() => void download()} />
      {report ? (
        <div className="dashboard">
          <p className={`health health-${report.project_health ?? "unknown"}`}>
            Project health: {healthLabel(report.project_health)}
          </p>
          <p className="muted">
            As of {report.as_of_date ?? "today"}
            {report.planned_only ? " · planned data only" : ""}
          </p>
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
              {report[selected].length === 0 ? (
                <p>Empty</p>
              ) : (
                <ul>
                  {report[selected].map((item) => (
                    <li key={item}>{item}</li>
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

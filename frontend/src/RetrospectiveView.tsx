import { useMemo, useState } from "react";
import { downloadRetrospectiveReport, generateRetrospective, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import type { FileRecord, ProcessingResponse, RetrospectiveReport } from "./types";

type SectionKey = Exclude<keyof RetrospectiveReport, "request_handle" | "summary" | "planned_only">;

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: "schedule_variance", label: "Schedule variance" },
  { key: "milestone_delivery", label: "Milestone delivery" },
  { key: "task_completion", label: "Task completion" },
  { key: "what_went_well", label: "What went well" },
  { key: "what_went_poorly", label: "What went poorly" },
  { key: "lessons_learned", label: "Lessons learned" },
  { key: "recommendations", label: "Recommendations" },
];

function asReport(result: ProcessingResponse["result"]): RetrospectiveReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as RetrospectiveReport;
  return {
    summary: data.summary ?? "",
    planned_only: Boolean(data.planned_only),
    schedule_variance: data.schedule_variance ?? [],
    milestone_delivery: data.milestone_delivery ?? [],
    task_completion: data.task_completion ?? [],
    what_went_well: data.what_went_well ?? [],
    what_went_poorly: data.what_went_poorly ?? [],
    lessons_learned: data.lessons_learned ?? [],
    recommendations: data.recommendations ?? [],
  };
}

export function RetrospectiveView() {
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(
    "Upload a Microsoft Project (.mpp) file to generate a planned-versus-actual retrospective.",
  );
  const [selected, setSelected] = useState<SectionKey>("schedule_variance");

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
    setMessage("Generating the retrospective…");
    try {
      const result = await generateRetrospective(handle);
      setJob(result);
      setMessage(result.status === "succeeded" ? "Retrospective ready." : "Generation failed.");
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
      await retryJob("retrospective", uploaded.id);
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
      const blob = await downloadRetrospectiveReport(uploaded.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "retrospective.md";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Download failed");
    }
  }

  return (
    <section className="panel">
      <h2>Project Retrospective</h2>
      <p>{message}</p>
      <FileUploader
        disabled={busy}
        accept=".mpp,application/vnd.ms-project"
        label="Choose Microsoft Project file (.mpp)"
        endpoint="/api/v1/retrospective/uploads"
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
          {report.summary ? <p>{report.summary}</p> : null}
          <p className="muted">
            {report.planned_only
              ? "Planned data only — no actuals were present to compare."
              : "Planned versus actual comparison from the uploaded plan."}
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

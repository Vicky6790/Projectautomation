import { useMemo, useState } from "react";
import { analyzeSow, downloadSowReport, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import type { AnalysisReport, FileRecord, ProcessingResponse } from "./types";

type CategoryKey = Exclude<keyof AnalysisReport, "request_handle">;

const CATEGORIES: { key: CategoryKey; label: string }[] = [
  { key: "gray_areas", label: "Gray areas" },
  { key: "risks", label: "Risks" },
  { key: "missing_requirements", label: "Missing requirements" },
  { key: "assumptions", label: "Assumptions" },
  { key: "dependencies", label: "Dependencies" },
  { key: "clarification_questions", label: "Clarification questions" },
];

function asReport(result: ProcessingResponse["result"]): AnalysisReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as AnalysisReport;
  return {
    gray_areas: data.gray_areas ?? [],
    risks: data.risks ?? [],
    missing_requirements: data.missing_requirements ?? [],
    assumptions: data.assumptions ?? [],
    dependencies: data.dependencies ?? [],
    clarification_questions: data.clarification_questions ?? [],
  };
}

export function SowAnalyzerView() {
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Upload a SOW to start analysis.");
  const [selected, setSelected] = useState<CategoryKey>("gray_areas");

  const report = asReport(job?.result ?? null);
  const counts = useMemo(() => {
    if (!report) {
      return {};
    }
    return Object.fromEntries(
      CATEGORIES.map((category) => [category.key, (report[category.key] as string[]).length]),
    ) as Record<string, number>;
  }, [report]);

  async function runAnalysis(handle: string) {
    setBusy(true);
    setMessage("Analyzing the SOW…");
    try {
      const result = await analyzeSow(handle);
      setJob(result);
      setMessage(result.status === "succeeded" ? "Analysis complete." : "Analysis failed.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Analysis failed");
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
      await retryJob("sow", uploaded.id);
    } catch {
      // Analyze re-runs a failed handle even if retry is not needed.
    }
    await runAnalysis(uploaded.id);
  }

  async function download() {
    if (!uploaded) {
      return;
    }
    try {
      const blob = await downloadSowReport(uploaded.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sow-analysis.md";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Download failed");
    }
  }

  return (
    <section className="panel">
      <h2>SOW Analyzer</h2>
      <p>{message}</p>
      <FileUploader
        disabled={busy}
        onUploaded={(file) => {
          setUploaded(file);
          setJob(null);
          void runAnalysis(file.id);
        }}
        onError={setMessage}
      />
      {uploaded ? <p>File: {uploaded.filename}</p> : null}
      {busy ? <p className="processing">Processing…</p> : null}
      {job?.status === "failed" ? (
        <button type="button" onClick={() => void retry()} disabled={busy}>
          Retry analysis
        </button>
      ) : null}
      <ReportDownloadControl enabled={job?.status === "succeeded" && !busy} onDownload={() => void download()} />
      {report ? (
        <div className="findings">
          <ul className="categories">
            {CATEGORIES.map((category) => (
              <li key={category.key}>
                <button
                  type="button"
                  className={selected === category.key ? "active" : ""}
                  onClick={() => setSelected(category.key)}
                >
                  {category.label} ({counts[category.key] ?? 0})
                </button>
              </li>
            ))}
          </ul>
          <div className="category-detail">
            <h3>{CATEGORIES.find((category) => category.key === selected)?.label}</h3>
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
      ) : null}
    </section>
  );
}

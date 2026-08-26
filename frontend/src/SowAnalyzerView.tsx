import { useContext, useEffect, useMemo, useState } from "react";
import { analyzeSow, downloadSowReport, retryJob } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ReportDownloadControl } from "./components/ReportDownloadControl";
import { ShellMetaContext } from "./shellMeta";
import type { AnalysisReport, FileRecord, ProcessingResponse, SowFinding } from "./types";

type CategoryKey = Exclude<keyof AnalysisReport, "request_handle" | "processed_pages" | "summary">;

const ANALYZE_STAGES = [
  "Reading the file",
  "Extracting text",
  "Analyzing the SOW",
  "Rendering findings",
];

const CATEGORIES: { key: CategoryKey; label: string }[] = [
  { key: "gray_areas", label: "Gray areas" },
  { key: "risks", label: "Risks" },
  { key: "missing_requirements", label: "Missing requirements" },
  { key: "assumptions", label: "Assumptions" },
  { key: "dependencies", label: "Dependencies" },
  { key: "clarification_questions", label: "Clarification questions" },
];

function asFinding(item: string | SowFinding, category: string): SowFinding {
  if (typeof item === "string") {
    return {
      category,
      title: item,
      description: item,
      recommendation: "",
    };
  }
  return {
    category: item.category || category,
    priority: item.priority,
    title: item.title || item.description,
    description: item.description || item.title,
    recommendation: item.recommendation || "",
  };
}

function asFindings(items: Array<string | SowFinding> | undefined, category: string): SowFinding[] {
  return (items ?? []).map((item) => asFinding(item, category));
}

function asReport(result: ProcessingResponse["result"]): AnalysisReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as AnalysisReport;
  return {
    request_handle: data.request_handle,
    processed_pages: data.processed_pages ?? null,
    summary: data.summary ?? "",
    gray_areas: asFindings(data.gray_areas, "gray_areas"),
    risks: asFindings(data.risks, "risks"),
    missing_requirements: asFindings(data.missing_requirements, "missing_requirements"),
    assumptions: asFindings(data.assumptions, "assumptions"),
    dependencies: asFindings(data.dependencies, "dependencies"),
    clarification_questions: asFindings(data.clarification_questions, "clarification_questions"),
  };
}

export function SowAnalyzerView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [uploaded, setUploaded] = useState<FileRecord | null>(null);
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [message, setMessage] = useState("Upload a Statement of Work (PDF or Word), then start analysis.");
  const [selected, setSelected] = useState<CategoryKey>("gray_areas");

  const report = asReport(job?.result ?? null);
  const counts = useMemo(() => {
    if (!report) {
      return {} as Record<string, number>;
    }
    return Object.fromEntries(
      CATEGORIES.map((category) => [category.key, report[category.key].length]),
    ) as Record<string, number>;
  }, [report]);
  const totalFindings = useMemo(
    () => CATEGORIES.reduce((sum, category) => sum + (counts[category.key] ?? 0), 0),
    [counts],
  );

  useEffect(() => {
    setPageMeta(uploaded?.filename ? `File: ${uploaded.filename}` : "");
    return () => setPageMeta("");
  }, [setPageMeta, uploaded?.filename]);

  useEffect(() => {
    if (!busy) {
      setStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStage((current) => Math.min(current + 1, ANALYZE_STAGES.length - 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function runAnalysis(handle: string) {
    setBusy(true);
    setMessage("Reading the file, extracting text, analyzing the SOW, and rendering findings…");
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
      const { blob, filename } = await downloadSowReport(uploaded.id);
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

  const selectedCategory = CATEGORIES.find((category) => category.key === selected);
  const selectedFindings = report ? report[selected] : [];

  return (
    <section className="wsr-page">
      <header className="wsr-page-head">
        <h2>SOW Analyzer</h2>
        <p>Upload a Statement of Work and review AI findings by category.</p>
      </header>

      <div className="wsr-action-bar">
        {uploaded ? (
          <div className="file-chip">
            <span className="file-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path
                  d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
                <path
                  d="M14 3v6h6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <span>{uploaded.filename}</span>
            <button
              type="button"
              className="chip-clear"
              aria-label="Remove file"
              disabled={busy}
              onClick={() => {
                setUploaded(null);
                setJob(null);
                setMessage("Upload a Statement of Work (PDF or Word), then start analysis.");
              }}
            >
              ×
            </button>
          </div>
        ) : (
          <FileUploader
            variant="button"
            disabled={busy}
            onUploaded={(file) => {
              setUploaded(file);
              setJob(null);
              setMessage("File ready. Start analysis to review findings.");
            }}
            onError={setMessage}
          />
        )}
        <div className="wsr-action-buttons">
          <ReportDownloadControl
            enabled={job?.status === "succeeded" && !busy}
            label="Download analysis report"
            onDownload={() => void download()}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={!uploaded || busy}
            onClick={() => uploaded && void runAnalysis(uploaded.id)}
          >
            Start analysis
          </button>
        </div>
      </div>

      <p className="wsr-status-msg">{message}</p>
      {busy ? (
        <ol className="wsr-stages">
          {ANALYZE_STAGES.map((label, index) => (
            <li key={label} className={index <= stage ? "active" : ""}>
              {label}
            </li>
          ))}
        </ol>
      ) : null}
      {job?.status === "failed" ? (
        <button type="button" className="btn btn-outline" onClick={() => void retry()} disabled={busy}>
          Retry analysis
        </button>
      ) : null}

      {report ? (
        <div className="dashboard sow-dashboard">
          <section className="sow-summary">
            <div>
              <h3>Analysis summary</h3>
              <p className="muted">
                {report.summary || `${totalFindings} findings across six categories.`}
                {report.processed_pages != null
                  ? ` · Processed pages: ${report.processed_pages}`
                  : ""}
              </p>
            </div>
            <p className="sow-total">
              <strong>{totalFindings}</strong>
              <span>Total findings</span>
            </p>
          </section>

          <ul className="sow-category-grid">
            {CATEGORIES.map((category) => (
              <li key={category.key}>
                <button
                  type="button"
                  className={selected === category.key ? "active" : ""}
                  onClick={() => setSelected(category.key)}
                >
                  <span>{category.label}</span>
                  <strong>{counts[category.key] ?? 0}</strong>
                </button>
              </li>
            ))}
          </ul>

          <section className="sow-detail">
            <h3>{selectedCategory?.label}</h3>
            {selectedFindings.length === 0 ? (
              <p>No findings were identified.</p>
            ) : (
              <ul className="sow-findings">
                {selectedFindings.map((item, index) => (
                  <li key={`${item.title}-${index}`} className="sow-finding">
                    <p className="sow-finding-meta">
                      <span className="ai-tag">{selectedCategory?.label}</span>
                      {item.priority ? <span className={`sow-priority sow-priority-${item.priority}`}>{item.priority}</span> : null}
                    </p>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                    {item.recommendation ? (
                      <p className="sow-recommendation">
                        <strong>AI recommendation:</strong> {item.recommendation}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : (
        <div className="wsr-empty">
          <h3>No analysis yet</h3>
          <p>Upload a PDF or Word Statement of Work, then start analysis to review findings by category.</p>
        </div>
      )}
    </section>
  );
}

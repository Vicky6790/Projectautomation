import { useContext, useEffect, useMemo, useState } from "react";
import { compareDelayMapping } from "./api";
import { FileUploader } from "./components/FileUploader";
import { emptyComparison, fromWsrDelayMapping, listedItems } from "./delayMapping/service";
import { exportDelayMappingExcel, printDelayMappingSheet } from "./delayMapping/exportSheet";
import { ShellMetaContext } from "./shellMeta";
import type { FileRecord } from "./types";
import { shortDate } from "./wsrFormat";

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [planFile, setPlanFile] = useState<FileRecord | null>(null);
  const [result, setResult] = useState(emptyComparison());
  const [loading, setLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    setPageMeta(planFile?.filename || "");
    return () => setPageMeta("");
  }, [planFile?.filename, setPageMeta]);

  useEffect(() => {
    if (!planFile) {
      setResult(emptyComparison());
      setLoading(false);
      setCompareError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    compareDelayMapping(planFile.id)
      .then((mapping) => {
        if (cancelled) {
          return;
        }
        setResult(fromWsrDelayMapping(mapping));
        setCompareError(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResult(emptyComparison());
          setCompareError(error instanceof Error ? error.message : "Could not read the MPP file.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [planFile?.id]);

  const rows = useMemo(() => listedItems(result), [result]);
  const canExport = Boolean(planFile);

  return (
    <section className="dms-page">
      <div className="dms-head">
        <div>
          <p className="dms-kicker">Delay Mapping</p>
          <h1>DELAY MAPPING</h1>
          <p className="dms-sub">Tasks whose Baseline Finish is NA</p>
        </div>
        <div className="dms-actions dms-no-print">
          <button
            type="button"
            className="btn btn-outline"
            disabled={!canExport}
            onClick={() => exportDelayMappingExcel(result, rows)}
          >
            Export Excel
          </button>
          <button type="button" className="btn btn-outline" disabled={!canExport} onClick={() => printDelayMappingSheet()}>
            Export PDF
          </button>
          <button type="button" className="btn btn-primary" disabled={!canExport} onClick={() => printDelayMappingSheet()}>
            Print
          </button>
        </div>
      </div>

      <div className="dms-uploads dms-uploads-single dms-no-print">
        <article className="dms-upload-slot">
          <p className="dms-kicker">Project MPP</p>
          {planFile ? (
            <div className="dms-file">
              <span className="material-symbols-outlined" aria-hidden="true">
                draft
              </span>
              <div>
                <strong>{planFile.filename}</strong>
                <em>Complete project plan</em>
              </div>
              <button type="button" className="chip-clear" aria-label="Remove Project MPP" onClick={() => setPlanFile(null)}>
                ×
              </button>
            </div>
          ) : (
            <FileUploader
              variant="card"
              accept=".mpp,application/vnd.ms-project"
              label="Insert Project MPP"
              hint="Microsoft Project (.mpp)"
              endpoint="/api/v1/wsr/uploads"
              onUploaded={setPlanFile}
              onError={setCompareError}
            />
          )}
        </article>
      </div>
      {!planFile ? (
        <p className="dms-sample dms-no-print" role="status">
          Insert one MPP. The Delay Sheet lists every task whose Baseline Finish is NA, N/A, or N.A.
          Blank Baseline Finish is not treated as NA.
        </p>
      ) : null}
      {compareError ? <p className="error">{compareError}</p> : null}
      {loading ? <p className="dms-loading dms-no-print">Reading the project schedule…</p> : null}

      <div className="dms-kpis">
        <Kpi label="Total tasks read" value={String(result.summary.tasksRead)} />
        <Kpi label="Baseline Finish = NA" value={String(result.summary.baselineFinishNaCount)} tone="additional" />
        <Kpi label="Delay Sheet rows" value={String(result.summary.delaySheetRows)} emphasis />
      </div>
      {result.summary.validationWarning ? <p className="error">{result.summary.validationWarning}</p> : null}

      <div className="dms-sheet">
        <div className="dms-table-wrap">
          <table className="dms-table">
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Task Name</th>
                <th>WBS</th>
                <th>Start</th>
                <th>Baseline Finish</th>
                <th>Finish</th>
                <th>Predecessors</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => (
                  <tr key={row.id} className="dms-row-additional">
                    <td>{row.taskId}</td>
                    <td>{row.taskName}</td>
                    <td>{row.wbs || ""}</td>
                    <td>{shortDate(row.currentStart)}</td>
                    <td>{row.baselineFinish || ""}</td>
                    <td>{shortDate(row.currentFinish)}</td>
                    <td>{row.predecessors.join(", ")}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="dms-empty">
                    {planFile ? "No tasks with Baseline Finish = NA" : "Insert an MPP to build the Delay Sheet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Kpi({
  label,
  value,
  emphasis,
  tone,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  tone?: "delay" | "additional";
}) {
  return (
    <article className={`dms-kpi${emphasis ? " dms-kpi-emphasis" : ""}${tone ? ` dms-kpi-${tone}` : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

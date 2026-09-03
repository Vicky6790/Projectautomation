import { useContext, useEffect, useMemo, useState } from "react";
import { compareDelayMapping } from "./api";
import { FileUploader } from "./components/FileUploader";
import { ModuleHero, ModuleLanding } from "./components/ModuleHero";
import { emptyComparison, fromWsrDelayMapping, listedItems } from "./delayMapping/service";
import { exportDelayMappingExcel, printDelayMappingSheet } from "./delayMapping/exportSheet";
import type { CompareMppResult, DelayMappingItem } from "./delayMapping/types";
import { ShellMetaContext } from "./shellMeta";
import type { FileRecord } from "./types";
import { delaySheetDate, unavailable } from "./wsrFormat";

type SortKey = "taskName" | "taskType" | "delayDays" | "owner";

const BUILD_STAGES = [
  "Reading the plan",
  "Tracing Go-Live predecessors",
  "Building the Delay Mapping sheet",
];

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [mppFile, setMppFile] = useState<FileRecord | null>(null);
  const [result, setResult] = useState<CompareMppResult>(emptyComparison());
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [failed, setFailed] = useState(false);
  const [message, setMessage] = useState("Upload a Microsoft Project (.mpp) file, then build Delay Mapping.");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("taskName");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("asc");
  const [drawer, setDrawer] = useState<DelayMappingItem | null>(null);

  useEffect(() => {
    setPageMeta(mppFile?.filename || "");
    return () => setPageMeta("");
  }, [mppFile?.filename, setPageMeta]);

  useEffect(() => {
    if (!loading) {
      setStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStage((current) => Math.min(current + 1, BUILD_STAGES.length - 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [loading]);

  function clearPlan() {
    setMppFile(null);
    setResult(emptyComparison());
    setReady(false);
    setFailed(false);
    setLoading(false);
    setDrawer(null);
    setMessage("Upload a Microsoft Project (.mpp) file, then build Delay Mapping.");
  }

  async function runCompare(handle: string) {
    setLoading(true);
    setFailed(false);
    setReady(false);
    setMessage("Reading the plan, tracing Go-Live predecessors, and building the sheet…");
    try {
      const mapping = await compareDelayMapping(handle);
      setResult(fromWsrDelayMapping(mapping));
      setReady(true);
      setMessage("Delay Mapping ready.");
    } catch (error: unknown) {
      setResult(emptyComparison());
      setReady(false);
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Could not build Delay Mapping.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrawer(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const allRows = useMemo(() => listedItems(result), [result]);
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = allRows.filter((row) => {
      if (!needle) {
        return true;
      }
      return (
        row.taskName.toLowerCase().includes(needle) ||
        (row.parentName || "").toLowerCase().includes(needle) ||
        (row.owner || "").toLowerCase().includes(needle)
      );
    });
    return [...filtered].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }, [allRows, query, sortDir, sortKey]);
  const groups = useMemo(() => groupByPhase(rows), [rows]);
  const totalShift = rows.reduce((sum, row) => sum + (row.delayDays ?? 0), 0);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((value) => (value === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "delayDays" ? "desc" : "asc");
  }

  const canExport = ready && !loading;
  const asOfLabel = result.summary.asOf ? delaySheetDate(result.summary.asOf) : "Unavailable";

  return (
    <section className="wsr-page dms-page">
      <ModuleHero
        tone="delay"
        icon="table_view"
        kicker="Delay Mapping"
        title="The tasks that actually move Go-Live"
        subtitle="Only Delay and Additional tasks on the predecessor path are listed. Total Count matches Actual Shift In Working Days."
      />

      <div className="wsr-upload-card dms-no-print">
        <div className="wsr-upload-inner">
          {mppFile ? (
            <div className="file-chip">
              <span className="wsr-upload-icon" aria-hidden="true">
                <span className="material-symbols-outlined">description</span>
              </span>
              <div>
                <p className="wsr-upload-title">{mppFile.filename}</p>
                <p className="wsr-upload-hint">Microsoft Project (.mpp)</p>
              </div>
              <button
                type="button"
                className="chip-clear"
                aria-label="Remove file"
                disabled={loading}
                onClick={clearPlan}
              >
                ×
              </button>
            </div>
          ) : (
            <FileUploader
              variant="card"
              disabled={loading}
              accept=".mpp,application/vnd.ms-project"
              label="Upload Project Plan"
              hint="Microsoft Project (.mpp)"
              endpoint="/api/v1/wsr/uploads"
              onUploaded={(file) => {
                setMppFile(file);
                setResult(emptyComparison());
                setReady(false);
                setFailed(false);
                setMessage("File ready. Build Delay Mapping to list the tasks that shift Go-Live.");
              }}
              onError={setMessage}
            />
          )}
          <div className="wsr-action-buttons">
            <button
              type="button"
              className="btn btn-outline"
              disabled={!canExport}
              onClick={() => exportDelayMappingExcel(result, rows)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                download
              </span>
              Export Excel
            </button>
            <button
              type="button"
              className="btn btn-outline"
              disabled={!canExport}
              onClick={() => printDelayMappingSheet()}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                picture_as_pdf
              </span>
              Export PDF
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!mppFile || loading}
              onClick={() => mppFile && void runCompare(mppFile.id)}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                table_view
              </span>
              Build Delay Mapping
            </button>
          </div>
        </div>
      </div>

      <p className="wsr-status-msg dms-no-print">{message}</p>
      {loading ? (
        <ol className="wsr-stages dms-no-print">
          {BUILD_STAGES.map((label, index) => (
            <li key={label} className={index <= stage ? "active" : ""}>
              {label}
            </li>
          ))}
        </ol>
      ) : null}
      {failed ? (
        <button
          type="button"
          className="btn btn-outline dms-no-print"
          onClick={() => mppFile && void runCompare(mppFile.id)}
          disabled={loading || !mppFile}
        >
          Retry mapping
        </button>
      ) : null}

      {ready ? (
        <>
      <table className="dms-summary">
        <tbody>
          <SummaryRow label="Baselined Go-Live Date" value={delaySheetDate(result.summary.baselineGoLive)} />
          <SummaryRow
            label={`Current Go-Live Date (As On ${asOfLabel})`}
            value={delaySheetDate(result.summary.currentGoLive)}
          />
          <SummaryRow
            label={`Shift In Working Days (As On ${asOfLabel})`}
            value={shiftLabel(result.summary.shiftWorkingDays)}
          />
          <SummaryRow label="Holidays In Above Duration" value={countLabel(result.summary.holidays)} />
          <SummaryRow
            label={`Actual Shift In Working Days (As On ${asOfLabel})`}
            value={shiftLabel(result.summary.actualShiftWorkingDays)}
          />
        </tbody>
      </table>

      <div className="dms-sheet">
        <div className="dms-toolbar dms-no-print">
          <label className="dms-search">
            Search
            <input
              type="search"
              value={query}
              placeholder="Search tasks..."
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>

        <div className="dms-table-wrap">
          <table className="dms-table">
            <thead>
              <tr>
                <SortHeader label="Task Name" active={sortKey === "taskName"} dir={sortDir} onClick={() => toggleSort("taskName")} />
                <SortHeader label="Task Type?" active={sortKey === "taskType"} dir={sortDir} onClick={() => toggleSort("taskType")} />
                <SortHeader
                  label="Shift Days Count"
                  active={sortKey === "delayDays"}
                  dir={sortDir}
                  onClick={() => toggleSort("delayDays")}
                />
                <SortHeader label="Owner" active={sortKey === "owner"} dir={sortDir} onClick={() => toggleSort("owner")} />
              </tr>
            </thead>
            <tbody>
              {groups.length ? (
                groups.map((group) => (
                  <PhaseGroup
                    key={group.phase}
                    group={group}
                    onOpen={setDrawer}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="dms-empty">
                    {allRows.length === 0
                      ? "No Delay or Additional tasks on the Go-Live predecessor path shift the timeline."
                      : "No tasks match the current search."}
                  </td>
                </tr>
              )}
            </tbody>
            {groups.length ? (
              <tfoot>
                <tr className="dms-total-row">
                  <td colSpan={2}>Total Count</td>
                  <td>{totalShift}</td>
                  <td />
                </tr>
              </tfoot>
            ) : null}
          </table>
        </div>
      </div>

      {drawer ? (
        <div className="dms-drawer-root dms-no-print">
          <button type="button" className="dms-drawer-mask" aria-label="Close details" onClick={() => setDrawer(null)} />
          <aside className="dms-drawer" role="dialog" aria-modal="true">
            <header className="dms-drawer-head">
              <div>
                <p className="dms-kicker">{drawer.taskType}</p>
                <h2>{drawer.taskName}</h2>
              </div>
              <button type="button" className="dms-icon-btn" onClick={() => setDrawer(null)} aria-label="Close">
                <span className="material-symbols-outlined">close</span>
              </button>
            </header>
            <dl className="dms-facts">
              <Fact label="Task Type?" value={drawer.taskType} />
              <Fact label="Shift Days Count" value={drawer.delayDays == null ? "Unavailable" : String(drawer.delayDays)} />
              <Fact label="Owner" value={unavailable(drawer.owner)} />
              <Fact label="Baseline Finish" value={delaySheetDate(drawer.plannedFinish)} />
              <Fact label="Finish" value={delaySheetDate(drawer.actualFinish)} />
              <Fact label="Predecessors" value={drawer.predecessorNames.join(", ") || "Unavailable"} />
              <Fact label="Phase" value={unavailable(drawer.parentName)} />
              <Fact label="Reason" value={unavailable(drawer.evidence)} />
            </dl>
          </aside>
        </div>
      ) : null}
        </>
      ) : (
        <ModuleLanding
          tone="delay"
          steps={[
            { icon: "upload_file", title: "Upload the plan", copy: "Microsoft Project (.mpp). The live file stays the source of truth." },
            { icon: "account_tree", title: "Build Delay Mapping", copy: "Predecessors, Baseline Finish, Finish, and Duration decide who shifts Go-Live." },
            { icon: "flag", title: "Review and export", copy: "Total Count matches Actual Shift In Working Days. Export Excel or PDF when you are ready." },
          ]}
        />
      )}
    </section>
  );
}

function PhaseGroup({
  group,
  onOpen,
}: {
  group: { phase: string; rows: DelayMappingItem[] };
  onOpen: (row: DelayMappingItem) => void;
}) {
  return (
    <>
      <tr className="dms-phase-row">
        <td colSpan={4}>{group.phase}</td>
      </tr>
      {group.rows.map((row) => (
        <tr
          key={row.id}
          className={row.taskType === "Delay" ? "dms-row-delay" : "dms-row-additional"}
          onClick={() => onOpen(row)}
        >
          <td>{row.taskName}</td>
          <td>
            <span className={row.taskType === "Delay" ? "dms-type-delay" : "dms-type-additional"}>
              {row.taskType}
            </span>
          </td>
          <td>{row.delayDays == null ? "Unavailable" : String(row.delayDays)}</td>
          <td>{unavailable(row.owner)}</td>
        </tr>
      ))}
    </>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <th>{label}</th>
      <td>{value}</td>
    </tr>
  );
}

function SortHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <th>
      <button type="button" className={active ? "is-active" : undefined} onClick={onClick}>
        {label}
        {active ? (dir === "asc" ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function groupByPhase(rows: DelayMappingItem[]): { phase: string; rows: DelayMappingItem[] }[] {
  const groups: { phase: string; rows: DelayMappingItem[] }[] = [];
  for (const row of rows) {
    const phase = row.parentName || "Other";
    const last = groups[groups.length - 1];
    if (last && last.phase === phase) {
      last.rows.push(row);
    } else {
      groups.push({ phase, rows: [row] });
    }
  }
  return groups;
}

function shiftLabel(value: number | null): string {
  if (value == null) {
    return "Unavailable";
  }
  return `${value} days shift`;
}

function countLabel(value: number | null): string {
  return value == null ? "Unavailable" : String(value);
}

function compareRows(a: DelayMappingItem, b: DelayMappingItem, key: SortKey, dir: "asc" | "desc"): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "delayDays") {
    return sign * ((a.delayDays ?? -1) - (b.delayDays ?? -1));
  }
  if (key === "taskType") {
    return sign * a.taskType.localeCompare(b.taskType);
  }
  if (key === "owner") {
    return sign * (a.owner || "").localeCompare(b.owner || "");
  }
  const phase = (a.parentName || "").localeCompare(b.parentName || "");
  if (phase) {
    return sign * phase;
  }
  return sign * a.taskName.localeCompare(b.taskName);
}

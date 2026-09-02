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

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [mppFile, setMppFile] = useState<FileRecord | null>(null);
  const [result, setResult] = useState<CompareMppResult>(emptyComparison());
  const [loading, setLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("taskName");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("asc");
  const [drawer, setDrawer] = useState<DelayMappingItem | null>(null);

  useEffect(() => {
    setPageMeta(mppFile?.filename || "");
    return () => setPageMeta("");
  }, [mppFile?.filename, setPageMeta]);

  useEffect(() => {
    if (!mppFile) {
      setResult(emptyComparison());
      setLoading(false);
      setCompareError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    compareDelayMapping(mppFile.id)
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
          setCompareError(error instanceof Error ? error.message : "Could not build Delay Mapping.");
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
  }, [mppFile?.id]);

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

  const canExport = Boolean(mppFile);
  const asOfLabel = result.summary.asOf ? delaySheetDate(result.summary.asOf) : "Unavailable";

  if (!mppFile) {
    return (
      <section className="dms-page">
        <ModuleHero
          tone="delay"
          icon="table_view"
          kicker="Delay Mapping"
          title="The tasks that actually move Go-Live"
          subtitle="Only Delay and Additional tasks on the predecessor path are listed. Total Count matches Actual Shift In Working Days."
        />
        <ModuleLanding
          tone="delay"
          steps={[
            { icon: "label", title: "Mark the plan", copy: "Set Delay And Or Additional to Delay or Additional." },
            { icon: "account_tree", title: "Read the chain", copy: "Predecessors, Baseline Finish, Finish, and Duration decide who shifts Go-Live." },
            { icon: "flag", title: "Match the shift", copy: "The sheet lists the driving tasks so Total Count equals the Go-Live shift." },
          ]}
        >
          <article className="dms-landing-upload">
            <p className="mod-kicker">Project plan</p>
            <h2>Insert Microsoft Project (.mpp)</h2>
            <p>The summary and task table stay empty until a plan is uploaded.</p>
            <MppSlot
              title="MPP"
              hint="Microsoft Project plan"
              file={mppFile}
              onUploaded={setMppFile}
              onClear={() => setMppFile(null)}
              onError={setCompareError}
            />
            {compareError ? <p className="error">{compareError}</p> : null}
          </article>
        </ModuleLanding>
      </section>
    );
  }

  return (
    <section className="dms-page">
      <ModuleHero
        tone="delay"
        icon="table_view"
        kicker="Delay Mapping"
        title="Delay Mapping Sheet"
        subtitle="Delay and Additional tasks that shift Go-Live, from Duration, Baseline Finish, Finish, and Predecessors"
        actions={
          <>
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
          </>
        }
      />

      <div className="dms-uploads dms-no-print">
        <MppSlot
          title="MPP"
          hint="Microsoft Project plan"
          file={mppFile}
          onUploaded={setMppFile}
          onClear={() => setMppFile(null)}
          onError={setCompareError}
        />
      </div>
      {compareError ? <p className="error">{compareError}</p> : null}
      {loading ? <p className="dms-loading dms-no-print">Building Delay Mapping…</p> : null}

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

function MppSlot({
  title,
  hint,
  file,
  onUploaded,
  onClear,
  onError,
}: {
  title: string;
  hint: string;
  file: FileRecord | null;
  onUploaded: (file: FileRecord) => void;
  onClear: () => void;
  onError: (message: string) => void;
}) {
  return (
    <article className="dms-upload-slot">
      <p className="dms-kicker">{title}</p>
      {file ? (
        <div className="dms-file">
          <span className="material-symbols-outlined" aria-hidden="true">
            draft
          </span>
          <div>
            <strong>{file.filename}</strong>
            <em>{hint}</em>
          </div>
          <button type="button" className="chip-clear" aria-label={`Remove ${title}`} onClick={onClear}>
            ×
          </button>
        </div>
      ) : (
        <FileUploader
          variant="card"
          accept=".mpp,application/vnd.ms-project"
          label={`Insert ${title}`}
          hint="Microsoft Project (.mpp)"
          endpoint="/api/v1/wsr/uploads"
          onUploaded={onUploaded}
          onError={onError}
        />
      )}
    </article>
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

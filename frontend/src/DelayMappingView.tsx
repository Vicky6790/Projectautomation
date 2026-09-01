import { useContext, useEffect, useMemo, useState } from "react";
import { compareDelayMapping } from "./api";
import { FileUploader } from "./components/FileUploader";
import {
  contributingItems,
  emptyComparison,
  fromWsrDelayMapping,
  listedItems,
} from "./delayMapping/service";
import { exportDelayMappingExcel, printDelayMappingSheet } from "./delayMapping/exportSheet";
import type { CompareMppResult, DelayMappingItem, DelayTaskType } from "./delayMapping/types";
import { ShellMetaContext } from "./shellMeta";
import type { FileRecord } from "./types";
import { shortDate, unavailable } from "./wsrFormat";

type SortKey = "taskName" | "taskType" | "impact" | "owner" | "finish";
type DrawerState =
  | { kind: "row"; item: DelayMappingItem }
  | { kind: "goLive" }
  | null;

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const [planFile, setPlanFile] = useState<FileRecord | null>(null);
  const [result, setResult] = useState<CompareMppResult>(emptyComparison());
  const [loading, setLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<"All" | DelayTaskType>("All");
  const [ownerFilter, setOwnerFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("finish");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("asc");
  const [drawer, setDrawer] = useState<DrawerState>(null);

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
  const owners = useMemo(
    () => unique(allRows.map((row) => row.owner).filter((value): value is string => Boolean(value))),
    [allRows],
  );
  const contributors = useMemo(() => contributingItems(result), [result]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = allRows.filter((row) => {
      if (typeFilter !== "All" && row.taskType !== typeFilter) {
        return false;
      }
      if (ownerFilter !== "All" && row.owner !== ownerFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return [row.taskName, row.owner, row.phase, joinNames(row.predecessors)].some((value) =>
        (value || "").toLowerCase().includes(needle),
      );
    });
    return [...filtered].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }, [allRows, ownerFilter, query, sortDir, sortKey, typeFilter]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((value) => (value === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "taskName" || key === "owner" || key === "taskType" ? "asc" : "desc");
  }

  const shift = result.summary.goLiveShift;
  const canExport = Boolean(planFile);
  const listedImpactTotal = rows.reduce((sum, row) => sum + (row.goLiveImpact || 0), 0);

  return (
    <section className="dms-page">
      <div className="dms-head">
        <div>
          <p className="dms-kicker">Delay Mapping</p>
          <h1>DELAY MAPPING</h1>
          <p className="dms-sub">Tasks that move the project deadline</p>
        </div>
        <div className="dms-actions dms-no-print">
          <button type="button" className="btn btn-outline" onClick={() => setDrawer({ kind: "goLive" })}>
            Why did Go-Live move?
          </button>
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
        <MppSlot
          title="Project MPP"
          hint="Complete current plan, including Baseline Finish"
          file={planFile}
          onUploaded={setPlanFile}
          onClear={() => setPlanFile(null)}
          onError={setCompareError}
        />
      </div>
      {!planFile ? (
        <p className="dms-sample dms-no-print" role="status">
          Insert one MPP. Delay Mapping uses Baseline Finish, Finish, and predecessor links from that file.
          Only DELAYED and ADDITIONAL tasks that reach Go-Live are listed.
        </p>
      ) : null}
      {compareError ? <p className="error">{compareError}</p> : null}
      {loading ? <p className="dms-loading dms-no-print">Reading the project schedule…</p> : null}

      <div className="dms-kpis">
        <Kpi label="Project Deadline" value={shortDate(result.summary.currentGoLive)} />
        <Kpi
          label="Identified Deadline Impact"
          value={shift == null ? "Unavailable" : `${shift > 0 ? "+" : ""}${shift} Working Days`}
          emphasis
        />
        <Kpi label="Delayed Tasks" value={String(result.summary.delayedTaskCount)} tone="delay" />
        <Kpi label="Additional Tasks" value={String(result.summary.additionalTaskCount)} tone="additional" />
      </div>
      {result.summary.calendarNote ? <p className="dms-note">{result.summary.calendarNote}</p> : null}
      {result.summary.validationWarning ? <p className="error">{result.summary.validationWarning}</p> : null}

      <div className="dms-sheet">
        <div className="dms-toolbar dms-no-print">
          <label>
            Task Type
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as "All" | DelayTaskType)}>
              <option>All</option>
              <option value="DELAYED">DELAYED</option>
              <option value="ADDITIONAL">ADDITIONAL</option>
            </select>
          </label>
          <label>
            Owner
            <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}>
              <option>All</option>
              {owners.map((owner) => (
                <option key={owner}>{owner}</option>
              ))}
            </select>
          </label>
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
                <SortHeader label="Task Type" active={sortKey === "taskType"} dir={sortDir} onClick={() => toggleSort("taskType")} />
                <th>Start</th>
                <th>Baseline Finish</th>
                <SortHeader label="Finish" active={sortKey === "finish"} dir={sortDir} onClick={() => toggleSort("finish")} />
                <SortHeader
                  label="Delay / Impact Days"
                  active={sortKey === "impact"}
                  dir={sortDir}
                  onClick={() => toggleSort("impact")}
                />
                <th>Predecessors</th>
                <SortHeader label="Owner" active={sortKey === "owner"} dir={sortDir} onClick={() => toggleSort("owner")} />
                <th>Impact Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => (
                  <tr
                    key={row.id}
                    className={row.taskType === "DELAYED" ? "dms-row-delay" : "dms-row-additional"}
                    onClick={() => setDrawer({ kind: "row", item: row })}
                  >
                    <td>{row.taskName}</td>
                    <td>
                      <span className={row.taskType === "DELAYED" ? "dms-badge dms-badge-delay" : "dms-badge dms-badge-additional"}>
                        {row.taskType}
                      </span>
                    </td>
                    <td>{shortDate(row.currentStart)}</td>
                    <td>{row.taskType === "ADDITIONAL" ? "N/A" : shortDate(row.baselineFinish)}</td>
                    <td>{shortDate(row.currentFinish)}</td>
                    <td>{impactCell(row)}</td>
                    <td>{joinNames(row.predecessors)}</td>
                    <td>{unavailable(row.owner)}</td>
                    <td>{row.evidence}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="dms-empty">
                    {allRows.length === 0
                      ? "No DELAYED or ADDITIONAL tasks contribute to the project deadline."
                      : "No tasks match the current filters."}
                  </td>
                </tr>
              )}
            </tbody>
            {rows.length ? (
              <tfoot>
                <tr className="dms-total-row">
                  <td>Total</td>
                  <td />
                  <td />
                  <td />
                  <td />
                  <td>{listedImpactTotal > 0 ? `+${listedImpactTotal} WD` : listedImpactTotal}</td>
                  <td />
                  <td />
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
            {drawer.kind === "row" ? (
              <RowDrawer item={drawer.item} onClose={() => setDrawer(null)} />
            ) : (
              <GoLiveDrawer
                result={result}
                contributors={contributors}
                onClose={() => setDrawer(null)}
                onOpen={(item) => setDrawer({ kind: "row", item })}
              />
            )}
          </aside>
        </div>
      ) : null}
    </section>
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

function RowDrawer({ item, onClose }: { item: DelayMappingItem; onClose: () => void }) {
  const delayed = item.taskType === "DELAYED";
  return (
    <>
      <header className="dms-drawer-head">
        <div>
          <p className="dms-kicker">{delayed ? "Delayed task" : "Additional task"}</p>
          <h2>{item.taskName}</h2>
        </div>
        <button type="button" className="dms-icon-btn" onClick={onClose} aria-label="Close">
          <span className="material-symbols-outlined">close</span>
        </button>
      </header>
      <dl className="dms-facts">
        <Fact label="Task Type" value={item.taskType} />
        <Fact label="Start" value={shortDate(item.currentStart)} />
        <Fact label="Baseline Finish" value={delayed ? shortDate(item.baselineFinish) : "N/A"} />
        <Fact label="Finish" value={shortDate(item.currentFinish)} />
        <Fact
          label="Delay / Impact Days"
          value={item.goLiveImpact > 0 ? `+${item.goLiveImpact} Working Days` : delayed ? "0 Working Days" : "N/A"}
        />
        <Fact label="Owner" value={unavailable(item.owner)} />
        <Fact label="Predecessors" value={joinNames(item.predecessors)} />
        <Fact label="Impact Reason" value={item.evidence} />
      </dl>
    </>
  );
}

function GoLiveDrawer({
  result,
  contributors,
  onClose,
  onOpen,
}: {
  result: CompareMppResult;
  contributors: DelayMappingItem[];
  onClose: () => void;
  onOpen: (item: DelayMappingItem) => void;
}) {
  const shift = result.goLiveImpact.totalShift;
  return (
    <>
      <header className="dms-drawer-head">
        <div>
          <p className="dms-kicker">Go-Live movement</p>
          <h2>Why did Go-Live move?</h2>
        </div>
        <button type="button" className="dms-icon-btn" onClick={onClose} aria-label="Close">
          <span className="material-symbols-outlined">close</span>
        </button>
      </header>
      <dl className="dms-facts">
        <Fact label="Project Deadline" value={shortDate(result.goLiveImpact.currentGoLive)} />
        <Fact label="Baseline Deadline" value={shortDate(result.goLiveImpact.baselineGoLive)} />
        <Fact
          label="Identified Deadline Impact"
          value={shift == null ? "Unavailable" : `+${shift} Working Days`}
        />
      </dl>
      <h3 className="dms-drawer-title">Contributing activities</h3>
      {contributors.length ? (
        <ul className="dms-contrib">
          {contributors.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => onOpen(item)}>
                <span className={item.taskType === "DELAYED" ? "dms-dot dms-dot-delay" : "dms-dot dms-dot-additional"} />
                <span>{item.taskName}</span>
                <strong>+{item.goLiveImpact} days</strong>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="dms-empty">No contributing activities are available from the plan.</p>
      )}
      <p className="dms-total">
        Identified Deadline Impact:{" "}
        <strong>{shift == null ? "Unavailable" : `+${shift} Working Days`}</strong>
      </p>
      <p className="dms-note">
        Sequential tasks on the same chain are not added together. Impact is the unique working-day
        contribution to the project deadline.
      </p>
    </>
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

function impactCell(row: DelayMappingItem): string {
  if (row.goLiveImpact > 0) {
    return `+${row.goLiveImpact} WD`;
  }
  return row.taskType === "ADDITIONAL" ? "N/A" : "0";
}

function joinNames(values: string[]): string {
  return values.length ? values.join(", ") : "Unavailable";
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function compareRows(a: DelayMappingItem, b: DelayMappingItem, key: SortKey, dir: "asc" | "desc"): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "impact") {
    return sign * ((a.goLiveImpact ?? 0) - (b.goLiveImpact ?? 0));
  }
  if (key === "finish") {
    return sign * (a.currentFinish || "").localeCompare(b.currentFinish || "");
  }
  const left = key === "taskName" ? a.taskName : key === "taskType" ? a.taskType : a.owner || "";
  const right = key === "taskName" ? b.taskName : key === "taskType" ? b.taskType : b.owner || "";
  return sign * left.localeCompare(right);
}

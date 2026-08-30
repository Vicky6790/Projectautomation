import { useContext, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { downloadWsrReport, getWsrRequest } from "./api";
import { compareMPP, contributingItems, fromWsrDelayMapping, listedItems } from "./delayMapping/service";
import { exportDelayMappingExcel, printDelayMappingSheet } from "./delayMapping/exportSheet";
import type { CompareMppResult, DelayMappingItem, DelayTaskType } from "./delayMapping/types";
import { ShellMetaContext } from "./shellMeta";
import { shortDate, unavailable } from "./wsrFormat";
import { asWsrReport, readWsrSession } from "./wsrSession";

type SortKey = "taskName" | "taskType" | "shiftDays" | "owner";
type DrawerState =
  | { kind: "row"; item: DelayMappingItem }
  | { kind: "goLive" }
  | null;

const EMPTY_RESULT = compareMPP();

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const session = readWsrSession();
  const handle = session?.handle ?? null;
  const [result, setResult] = useState<CompareMppResult>(EMPTY_RESULT);
  const [loading, setLoading] = useState(Boolean(handle));
  const [typeFilter, setTypeFilter] = useState<"All" | DelayTaskType>("All");
  const [ownerFilter, setOwnerFilter] = useState("All");
  const [phaseFilter, setPhaseFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("shiftDays");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    if (!handle) {
      setResult(compareMPP());
      setLoading(false);
      return;
    }
    let cancelled = false;
    getWsrRequest(handle)
      .then((job) => {
        if (cancelled) {
          return;
        }
        const report = asWsrReport(job.result ?? null);
        if (job.status === "succeeded" && report?.facts?.delay_mapping) {
          setResult(fromWsrDelayMapping(report.facts.delay_mapping));
          const identity = [report.facts.project_name, report.facts.project_owner]
            .filter(Boolean)
            .join(" · ");
          setPageMeta(identity);
        } else {
          setResult(compareMPP());
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResult(compareMPP());
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
  }, [handle, setPageMeta]);

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
  const phases = useMemo(() => unique(allRows.map((row) => row.phase).filter(Boolean)), [allRows]);
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
      if (phaseFilter !== "All" && row.phase !== phaseFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return [row.taskName, row.owner, row.phase].some((value) =>
        (value || "").toLowerCase().includes(needle),
      );
    });
    const sorted = [...filtered].sort((a, b) => compareRows(a, b, sortKey, sortDir));
    if (sortKey === "shiftDays" && sortDir === "desc") {
      sorted.sort((a, b) => {
        const impact = b.goLiveImpact - a.goLiveImpact;
        if (impact !== 0) {
          return impact;
        }
        return compareRows(a, b, "shiftDays", "desc");
      });
    }
    return sorted;
  }, [allRows, ownerFilter, phaseFilter, query, sortDir, sortKey, typeFilter]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((value) => (value === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "taskName" || key === "owner" || key === "taskType" ? "asc" : "desc");
  }

  async function downloadPdf() {
    setPdfError(null);
    if (!handle || result.source !== "live") {
      printDelayMappingSheet();
      return;
    }
    setPdfBusy(true);
    try {
      const { blob, filename } = await downloadWsrReport(handle, "delay_mapping");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setPdfError(error instanceof Error ? error.message : "PDF download failed");
    } finally {
      setPdfBusy(false);
    }
  }

  const shift = result.summary.goLiveShift;

  return (
    <section className="dms-page">
      <div className="dms-head">
        <div>
          <p className="dms-kicker">Delay Mapping</p>
          <h1>DELAY MAPPING</h1>
          <p className="dms-sub">Baseline vs Current Schedule Variance</p>
        </div>
        <div className="dms-actions dms-no-print">
          <button type="button" className="btn btn-outline" onClick={() => setDrawer({ kind: "goLive" })}>
            Why did Go-Live move?
          </button>
          <button type="button" className="btn btn-outline" onClick={() => exportDelayMappingExcel(result, rows)}>
            Export Excel
          </button>
          <button type="button" className="btn btn-outline" disabled={pdfBusy} onClick={() => void downloadPdf()}>
            {pdfBusy ? "Preparing PDF…" : "Export PDF"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => printDelayMappingSheet()}>
            Print
          </button>
        </div>
      </div>

      {!loading && result.source === "sample" ? (
        <p className="dms-sample dms-no-print" role="status">
          Sample comparison for the sheet layout.{" "}
          <Link to="/wsr">Generate a WSR from the current MPP</Link> to replace this with Baseline vs Current
          from the plan. Missing MPP values stay Unavailable.
        </p>
      ) : null}
      {pdfError ? <p className="error">{pdfError}</p> : null}
      {loading ? <p className="dms-loading dms-no-print">Loading delay mapping…</p> : null}

      <div className="dms-kpis">
        <Kpi label="Baseline Go-Live" value={shortDate(result.summary.baselineGoLive)} />
        <Kpi label="Current Go-Live" value={shortDate(result.summary.currentGoLive)} />
        <Kpi
          label="Go-Live Shift"
          value={shift == null ? "Unavailable" : `${shift > 0 ? "+" : ""}${shift} Working Days`}
          emphasis
        />
        <Kpi label="Delayed Tasks" value={String(result.summary.delayedTaskCount)} tone="delay" />
        <Kpi label="Additional Tasks" value={String(result.summary.additionalTaskCount)} tone="additional" />
      </div>
      {result.summary.calendarNote ? <p className="dms-note">{result.summary.calendarNote}</p> : null}

      <div className="dms-sheet">
        <div className="dms-toolbar dms-no-print">
          <label>
            Task Type
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as "All" | DelayTaskType)}>
              <option>All</option>
              <option>Delay</option>
              <option>Additional</option>
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
          <label>
            Phase
            <select value={phaseFilter} onChange={(event) => setPhaseFilter(event.target.value)}>
              <option>All</option>
              {phases.map((phase) => (
                <option key={phase}>{phase}</option>
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
                <SortHeader
                  label="Shift Days Count"
                  active={sortKey === "shiftDays"}
                  dir={sortDir}
                  onClick={() => toggleSort("shiftDays")}
                />
                <SortHeader label="Owner" active={sortKey === "owner"} dir={sortDir} onClick={() => toggleSort("owner")} />
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => (
                  <tr
                    key={row.id}
                    className={row.taskType === "Delay" ? "dms-row-delay" : "dms-row-additional"}
                    onClick={() => setDrawer({ kind: "row", item: row })}
                  >
                    <td>{row.taskName}</td>
                    <td>
                      <span className={row.taskType === "Delay" ? "dms-badge dms-badge-delay" : "dms-badge dms-badge-additional"}>
                        {row.taskType === "Delay" ? "Delay" : "Add."}
                      </span>
                    </td>
                    <td>{row.shiftDays == null ? "Unavailable" : row.shiftDays}</td>
                    <td>{unavailable(row.owner)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="dms-empty">
                    No Delay or Additional tasks match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
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
  const delay = item.taskType === "Delay";
  return (
    <>
      <header className="dms-drawer-head">
        <div>
          <p className="dms-kicker">{delay ? "Delay details" : "Additional task"}</p>
          <h2>{item.taskName}</h2>
        </div>
        <button type="button" className="dms-icon-btn" onClick={onClose} aria-label="Close">
          <span className="material-symbols-outlined">close</span>
        </button>
      </header>
      <dl className="dms-facts">
        <Fact label="Task" value={item.taskName} />
        <Fact label="Type" value={item.taskType.toUpperCase()} />
        {delay ? (
          <>
            <Fact label="Baseline Finish" value={shortDate(item.baselineFinish)} />
            <Fact label="Current Finish" value={shortDate(item.currentFinish)} />
            <Fact
              label="Shift"
              value={item.shiftDays == null ? "Unavailable" : `+${item.shiftDays} Working Days`}
            />
          </>
        ) : (
          <>
            <Fact label="Baseline" value="Not Present" />
            <Fact label="Current Start" value={shortDate(item.currentStart)} />
            <Fact label="Current Finish" value={shortDate(item.currentFinish)} />
          </>
        )}
        <Fact label="Owner" value={unavailable(item.owner)} />
        <Fact label="Predecessor" value={joinNames(item.predecessors)} />
        <Fact label="Successor" value={joinNames(item.successors)} />
        <Fact
          label="Go-Live Impact"
          value={item.goLiveImpact > 0 ? `+${item.goLiveImpact} Working Days` : "0 Working Days"}
        />
        <Fact label={delay ? "Evidence" : "Reason"} value={item.evidence} />
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
        <Fact label="Baseline Go-Live" value={shortDate(result.goLiveImpact.baselineGoLive)} />
        <Fact label="Current Go-Live" value={shortDate(result.goLiveImpact.currentGoLive)} />
        <Fact
          label="Total Shift"
          value={shift == null ? "Unavailable" : `+${shift} Working Days`}
        />
      </dl>
      <h3 className="dms-drawer-title">Contributing activities</h3>
      {contributors.length ? (
        <ul className="dms-contrib">
          {contributors.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => onOpen(item)}>
                <span className={item.taskType === "Delay" ? "dms-dot dms-dot-delay" : "dms-dot dms-dot-additional"} />
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
        Total Go-Live Impact:{" "}
        <strong>{shift == null ? "Unavailable" : `+${shift} Working Days`}</strong>
      </p>
      <p className="dms-note">
        Go-Live impact comes from Baseline Go-Live versus Current Go-Live. Task days are not summed
        when they overlap the same schedule movement.
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

function joinNames(values: string[]): string {
  return values.length ? values.join(", ") : "Unavailable";
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function compareRows(a: DelayMappingItem, b: DelayMappingItem, key: SortKey, dir: "asc" | "desc"): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "shiftDays") {
    return sign * ((a.shiftDays ?? -1) - (b.shiftDays ?? -1));
  }
  const left = key === "taskName" ? a.taskName : key === "taskType" ? a.taskType : a.owner || "";
  const right = key === "taskName" ? b.taskName : key === "taskType" ? b.taskType : b.owner || "";
  return sign * left.localeCompare(right);
}

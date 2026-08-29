import { useContext, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getWsrRequest } from "./api";
import { ShellMetaContext } from "./shellMeta";
import type { DelayMappingRow, DelayMappingSheet, WsrPlanFacts } from "./types";
import { shortDate, unavailable } from "./wsrFormat";
import { asWsrReport, readWsrSession } from "./wsrSession";

export function DelayMappingView() {
  const setPageMeta = useContext(ShellMetaContext);
  const session = readWsrSession();
  const handle = session?.handle ?? null;
  const [message, setMessage] = useState(
    session ? "Loading delay mapping from the generated WSR…" : "Generate a WSR to open the Delay Mapping Sheet.",
  );
  const [facts, setFacts] = useState<WsrPlanFacts | null>(null);

  useEffect(() => {
    if (!handle) {
      return;
    }
    let cancelled = false;
    getWsrRequest(handle)
      .then((job) => {
        if (cancelled) {
          return;
        }
        const report = asWsrReport(job.result ?? null);
        if (job.status !== "succeeded" || !report?.facts) {
          setMessage("Generate a WSR to open the Delay Mapping Sheet.");
          return;
        }
        setFacts(report.facts);
        setMessage("");
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Could not load the generated WSR.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [handle]);

  useEffect(() => {
    const identity = [facts?.project_name, facts?.project_owner].filter(Boolean).join(" · ");
    setPageMeta(identity);
    return () => setPageMeta("");
  }, [facts?.project_name, facts?.project_owner, setPageMeta]);

  const mapping: DelayMappingSheet = facts?.delay_mapping ?? {};
  const rows = mapping.rows ?? [];
  const groups = useMemo(() => groupByPhase(rows), [rows]);
  const asOf = facts?.as_of_date;
  const rowTotal =
    mapping.actual_shift_working_days ??
    mapping.total_delayed_days ??
    rows.reduce((sum, row) => sum + (row.shift_days ?? row.delay_days ?? 0), 0);

  if (!facts) {
    return (
      <section className="delay-page">
        <div className="delay-empty">
          <h2>Delay Mapping Sheet</h2>
          <p>{message}</p>
          <Link className="btn btn-primary" to="/wsr">
            Back to WSR & Insights
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="delay-page">
      <div className="delay-head">
        <div>
          <div className="delay-crumb">
            <Link to="/wsr">WSR & Insights</Link>
            <span className="material-symbols-outlined" aria-hidden="true">
              chevron_right
            </span>
            <span>Delay Mapping Sheet</span>
          </div>
          <h1>Delay Mapping Sheet</h1>
          <p>
            Working-day Go-Live shift, plus only Delay or Additional MPP tasks that moved that date.
            Shift Days Count totals the same working days as Actual Shift.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => downloadDelayMappingSheet(mapping, asOf)}
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            download
          </span>
          Download Sheet
        </button>
      </div>

      <div className="delay-summary-card">
        <table className="delay-summary">
          <tbody>
            <tr>
              <th>Baselined Go-Live Date</th>
              <td>{shortDate(mapping.baseline_go_live)}</td>
            </tr>
            <tr>
              <th>Current Go-Live Date{asOf ? ` (As On ${shortDate(asOf)})` : ""}</th>
              <td>{shortDate(mapping.current_go_live)}</td>
            </tr>
            <tr>
              <th>Shift In Working Days{asOf ? ` (As On ${shortDate(asOf)})` : ""}</th>
              <td>{shiftLabel(mapping.shift_working_days)}</td>
            </tr>
            <tr>
              <th>Holidays In Above Duration</th>
              <td>{unavailableCount(mapping.holidays)}</td>
            </tr>
            <tr>
              <th>Actual Shift In Working Days{asOf ? ` (As On ${shortDate(asOf)})` : ""}</th>
              <td className="delay-actual">{shiftLabel(mapping.actual_shift_working_days)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="delay-table-card">
        <div className="delay-table-head">
          <div className="delay-table-title">
            <span className="wsr-num" aria-hidden="true">
              <span className="material-symbols-outlined">table_rows</span>
            </span>
            <h2>Detailed Mapping</h2>
          </div>
        </div>
        {rows.length ? (
          <div className="delay-table-wrap">
            <table className="delay-table delay-sheet">
              <thead>
                <tr>
                  <th>Task Name</th>
                  <th>Task Type</th>
                  <th>Shift Days Count</th>
                  <th>Owner</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <PhaseGroup key={group.name} group={group} />
                ))}
                <tr className="delay-total-row">
                  <td>Total Count</td>
                  <td />
                  <td>
                    <strong>{rowTotal}</strong>
                  </td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="delay-empty-rows">No Delay or Additional tasks impacting the Go-Live shift</p>
        )}
      </div>
    </section>
  );
}

function PhaseGroup({ group }: { group: { name: string; rows: DelayMappingRow[] } }) {
  return (
    <>
      <tr className="delay-phase-row">
        <td colSpan={4}>{group.name}</td>
      </tr>
      {group.rows.map((row, index) => {
        const days = row.shift_days ?? row.delay_days;
        const type = row.task_type || (row.kind === "phase" ? "delay" : undefined);
        return (
          <tr key={`${group.name}-${row.wbs || row.name}-${index}`} className={type ? `delay-type-${type}` : undefined}>
            <td>{row.name}</td>
            <td>{type ? capitalize(type) : "Unavailable"}</td>
            <td>{days == null ? "Unavailable" : days}</td>
            <td>{unavailable(row.owner)}</td>
          </tr>
        );
      })}
    </>
  );
}

function groupByPhase(rows: DelayMappingRow[]): { name: string; rows: DelayMappingRow[] }[] {
  const groups: { name: string; rows: DelayMappingRow[] }[] = [];
  const indexByName = new Map<string, number>();
  for (const row of rows) {
    const name = row.parent_name?.trim() || (row.kind === "phase" ? row.name : "Other");
    const existing = indexByName.get(name);
    if (existing == null) {
      indexByName.set(name, groups.length);
      groups.push({ name, rows: [row] });
    } else {
      groups[existing].rows.push(row);
    }
  }
  return groups;
}

function shiftLabel(value: number | null | undefined): string {
  if (value == null) {
    return "Unavailable";
  }
  return value === 1 ? "1 day shift" : `${value} days shift`;
}

function unavailableCount(value: number | null | undefined): string {
  return value == null ? "Unavailable" : String(value);
}

function capitalize(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

function csvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function downloadDelayMappingSheet(mapping: DelayMappingSheet, asOf?: string) {
  const rows = mapping.rows ?? [];
  const summary = [
    ["Baselined Go-Live Date", mapping.baseline_go_live?.slice(0, 10) || ""],
    ["Current Go-Live Date", mapping.current_go_live?.slice(0, 10) || ""],
    ["As Of", asOf?.slice(0, 10) || ""],
    ["Shift In Working Days", mapping.shift_working_days == null ? "" : String(mapping.shift_working_days)],
    ["Holidays In Above Duration", mapping.holidays == null ? "" : String(mapping.holidays)],
    [
      "Actual Shift In Working Days",
      mapping.actual_shift_working_days == null ? "" : String(mapping.actual_shift_working_days),
    ],
    [],
    ["Phase", "Task Name", "Task Type", "Shift Days Count", "Owner"],
  ];
  const body = rows.map((row) => [
    row.parent_name || "",
    row.name,
    row.task_type || "",
    row.shift_days == null && row.delay_days == null ? "" : String(row.shift_days ?? row.delay_days),
    row.owner || "",
  ]);
  const total =
    mapping.actual_shift_working_days ??
    mapping.total_delayed_days ??
    rows.reduce((sum, row) => sum + (row.shift_days ?? row.delay_days ?? 0), 0);
  const csv = [...summary, ...body, ["", "Total Count", "", String(total), ""]]
    .map((line) => line.map(csvCell).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "delay-mapping-sheet.csv";
  link.click();
  URL.revokeObjectURL(url);
}

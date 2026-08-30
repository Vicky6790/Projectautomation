import { useMemo } from "react";
import type { DelayMappingRow, DelayMappingSheet } from "../types";
import { shortDate, unavailable } from "../wsrFormat";

const RECONCILE_WARNING =
  "Delay mapping total does not reconcile with the calculated Go-Live shift. PM validation required.";

export function DelayMappingPanel({
  mapping,
}: {
  mapping: DelayMappingSheet;
  asOf?: string;
}) {
  const rows = mapping.rows ?? [];
  const groups = useMemo(() => groupByPhase(mapping.rows ?? []), [mapping.rows]);
  const actual = mapping.actual_shift_working_days ?? mapping.net_working_day_shift;
  const total =
    mapping.total_delayed_days ??
    rows.reduce((sum, row) => sum + (row.shift_days ?? row.delay_days ?? 0), 0);
  const warning =
    mapping.matching_requires_validation
      ? mapping.reconciliation_warning || RECONCILE_WARNING
      : null;

  return (
    <div className="delay-engine">
      <div className="delay-summary-card">
        <h2 className="delay-block-title">Go-Live Date Shift</h2>
        <table className="delay-summary">
          <tbody>
            <tr>
              <th>Baselined Go-Live Date</th>
              <td>{shortDate(mapping.baseline_go_live)}</td>
            </tr>
            <tr>
              <th>Current Go-Live Date</th>
              <td>{shortDate(mapping.current_go_live)}</td>
            </tr>
            <tr>
              <th>Shift In Working Days</th>
              <td>{unavailableCount(mapping.shift_working_days ?? mapping.gross_working_day_shift)}</td>
            </tr>
            <tr>
              <th>Holidays In Above Duration</th>
              <td>{unavailableCount(mapping.holidays)}</td>
            </tr>
            <tr>
              <th>Actual Shift In Working Days</th>
              <td className="delay-actual">{unavailableCount(actual)}</td>
            </tr>
          </tbody>
        </table>
        {mapping.calendar_source === "weekdays_fallback" ? (
          <p className="delay-calendar-note">
            Working days use the system weekday calendar (project calendar unavailable).
          </p>
        ) : null}
      </div>

      {warning ? (
        <p className="delay-unattributed" role="status">
          {warning}
        </p>
      ) : null}

      <div className="delay-table-card">
        <div className="delay-table-head">
          <div className="delay-table-title">
            <span className="wsr-num" aria-hidden="true">
              <span className="material-symbols-outlined">table_rows</span>
            </span>
            <h2>Delay Mapping</h2>
          </div>
        </div>
        {rows.length ? (
          <div className="delay-table-wrap">
            <table className="delay-table delay-sheet">
              <thead>
                <tr>
                  <th>Task Name</th>
                  <th>Task Type</th>
                  <th>Baseline Finish</th>
                  <th>Finish</th>
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
                  <td />
                  <td />
                  <td>
                    <strong>{total}</strong>
                  </td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="delay-empty-rows">No Delay or Additional tasks from Baseline Finish versus Finish</p>
        )}
      </div>
    </div>
  );
}

function PhaseGroup({ group }: { group: { name: string; rows: DelayMappingRow[] } }) {
  return (
    <>
      <tr className="delay-phase-row">
        <td colSpan={6}>{group.name}</td>
      </tr>
      {group.rows.map((row, index) => {
        const days = row.shift_days ?? row.delay_days;
        const type = row.task_type;
        return (
          <tr key={`${group.name}-${row.wbs || row.name}-${index}`} className={type ? `delay-type-${type}` : undefined}>
            <td>{row.name}</td>
            <td>{type ? capitalize(type) : "Unavailable"}</td>
            <td>{shortDate(row.planned_finish)}</td>
            <td>{shortDate(row.revised_finish)}</td>
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

function unavailableCount(value: number | null | undefined): string {
  return value == null ? "Unavailable" : String(value);
}

function capitalize(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

export function downloadDelayMappingSheet(mapping: DelayMappingSheet, asOf?: string) {
  const rows = mapping.rows ?? [];
  const actual = mapping.actual_shift_working_days ?? mapping.net_working_day_shift;
  const total =
    mapping.total_delayed_days ??
    rows.reduce((sum, row) => sum + (row.shift_days ?? row.delay_days ?? 0), 0);
  const shift = mapping.shift_working_days ?? mapping.gross_working_day_shift;
  const summary = [
    ["GO-LIVE DATE SHIFT"],
    ["Baselined Go-Live Date", mapping.baseline_go_live?.slice(0, 10) || ""],
    ["Current Go-Live Date", mapping.current_go_live?.slice(0, 10) || ""],
    asOf ? ["As Of", asOf.slice(0, 10)] : [],
    ["Shift In Working Days", shift == null ? "" : String(shift)],
    ["Holidays In Above Duration", mapping.holidays == null ? "" : String(mapping.holidays)],
    ["Actual Shift In Working Days", actual == null ? "" : String(actual)],
    mapping.reconciliation_warning ? ["Warning", mapping.reconciliation_warning] : [],
    [],
    ["DELAY MAPPING"],
    ["Task Name", "Task Type", "Baseline Finish", "Finish", "Shift Days Count", "Owner"],
  ].filter((line) => line.length > 0);
  const body: string[][] = [];
  for (const group of groupByPhase(rows)) {
    body.push([group.name, "", "", "", "", ""]);
    for (const row of group.rows) {
      const days = row.shift_days ?? row.delay_days;
      body.push([
        row.name,
        row.task_type ? capitalize(row.task_type) : "",
        row.planned_finish?.slice(0, 10) || "",
        row.revised_finish?.slice(0, 10) || "",
        days == null ? "" : String(days),
        row.owner || "",
      ]);
    }
  }
  const csv = [...summary, ...body, ["Total Count", "", "", "", String(total), ""]]
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

function csvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

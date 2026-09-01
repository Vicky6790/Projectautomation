import { useMemo } from "react";
import type { DelayMappingRow, DelayMappingSheet } from "../types";
import { shortDate, unavailable } from "../wsrFormat";

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
    rows.reduce((sum, row) => sum + (row.go_live_impact_days ?? 0), 0);
  const warning = mapping.reconciliation_warning || null;

  return (
    <div className="delay-engine">
      <div className="delay-summary-card">
        <h2 className="delay-block-title">Project Deadline</h2>
        <table className="delay-summary">
          <tbody>
            <tr>
              <th>Project Deadline</th>
              <td>{shortDate(mapping.current_go_live)}</td>
            </tr>
            <tr>
              <th>Baseline Deadline</th>
              <td>{shortDate(mapping.baseline_go_live)}</td>
            </tr>
            <tr>
              <th>Identified Deadline Impact</th>
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
                  <th>Start</th>
                  <th>Baseline Finish</th>
                  <th>Finish</th>
                  <th>Delay / Impact Days</th>
                  <th>Predecessors</th>
                  <th>Owner</th>
                  <th>Impact Reason</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <PhaseGroup key={group.name} group={group} />
                ))}
                <tr className="delay-total-row">
                  <td>Total</td>
                  <td />
                  <td />
                  <td />
                  <td />
                  <td>
                    <strong>{total}</strong>
                  </td>
                  <td />
                  <td />
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="delay-empty-rows">No driving Delay or Additional tasks from dates and dependencies</p>
        )}
      </div>
    </div>
  );
}

function PhaseGroup({ group }: { group: { name: string; rows: DelayMappingRow[] } }) {
  return (
    <>
      <tr className="delay-phase-row">
        <td colSpan={9}>{group.name}</td>
      </tr>
      {group.rows.map((row, index) => {
        const type = row.task_type;
        const typeLabel = type === "delay" ? "DELAYED" : type === "additional" ? "ADDITIONAL" : type ? type.toUpperCase() : "Unavailable";
        const impact = row.go_live_impact_days;
        const impactLabel =
          type === "additional" && !impact ? "N/A" : impact == null ? "Unavailable" : `+${impact} WD`;
        const baseline = type === "additional" ? "N/A" : shortDate(row.planned_finish);
        return (
          <tr key={`${group.name}-${row.wbs || row.name}-${index}`} className={type ? `delay-type-${type}` : undefined}>
            <td>{row.name}</td>
            <td>{typeLabel}</td>
            <td>{shortDate(row.revised_start)}</td>
            <td>{baseline}</td>
            <td>{shortDate(row.revised_finish)}</td>
            <td>{impactLabel}</td>
            <td>{row.predecessor_names?.join(", ") || "Unavailable"}</td>
            <td>{unavailable(row.owner)}</td>
            <td>{row.evidence_reason || row.primary_reason || "Unavailable"}</td>
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

export function downloadDelayMappingSheet(mapping: DelayMappingSheet, asOf?: string) {
  const rows = mapping.rows ?? [];
  const actual = mapping.actual_shift_working_days ?? mapping.net_working_day_shift;
  const total =
    mapping.total_delayed_days ??
    rows.reduce((sum, row) => sum + (row.go_live_impact_days ?? 0), 0);
  const summary = [
    ["PROJECT DEADLINE"],
    ["Project Deadline", mapping.current_go_live?.slice(0, 10) || ""],
    ["Baseline Deadline", mapping.baseline_go_live?.slice(0, 10) || ""],
    asOf ? ["As Of", asOf.slice(0, 10)] : [],
    ["Identified Deadline Impact", actual == null ? "" : String(actual)],
    mapping.reconciliation_warning ? ["Warning", mapping.reconciliation_warning] : [],
    [],
    ["DELAY MAPPING"],
    [
      "Task Name",
      "Task Type",
      "Start",
      "Baseline Finish",
      "Finish",
      "Delay / Impact Days",
      "Predecessors",
      "Owner",
      "Impact Reason",
    ],
  ].filter((line) => line.length > 0);
  const body: string[][] = [];
  for (const group of groupByPhase(rows)) {
    body.push([group.name, "", "", "", "", "", "", "", ""]);
    for (const row of group.rows) {
      const type = row.task_type === "delay" ? "DELAYED" : row.task_type === "additional" ? "ADDITIONAL" : row.task_type || "";
      const impact = row.go_live_impact_days;
      body.push([
        row.name,
        type,
        row.revised_start?.slice(0, 10) || "",
        row.task_type === "additional" ? "N/A" : row.planned_finish?.slice(0, 10) || "",
        row.revised_finish?.slice(0, 10) || "",
        impact == null ? "" : String(impact),
        (row.predecessor_names || []).join(", "),
        row.owner || "",
        row.evidence_reason || row.primary_reason || "",
      ]);
    }
  }
  const csv = [...summary, ...body, ["Total", "", "", "", "", String(total), "", "", ""]]
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

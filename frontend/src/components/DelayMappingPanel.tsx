import { useMemo } from "react";
import type { DelayAttributionBucket, DelayMappingRow, DelayMappingSheet } from "../types";
import { shortDate, unavailable } from "../wsrFormat";

export function DelayMappingPanel({
  mapping,
  asOf,
}: {
  mapping: DelayMappingSheet;
  asOf?: string;
}) {
  const rows = mapping.rows ?? [];
  const groups = useMemo(() => groupByPhase(rows), [rows]);
  const net = mapping.net_working_day_shift ?? mapping.actual_shift_working_days;
  const attributed = mapping.attributed_shift_days ?? mapping.total_delayed_days ?? 0;
  const unattributed = mapping.unattributed_shift_days ?? 0;
  const asOfLabel = asOf ? ` (As On ${shortDate(asOf)})` : "";

  return (
    <div className="delay-engine">
      <div className="delay-summary-card">
        <table className="delay-summary">
          <tbody>
            <tr>
              <th>Baseline Go-Live Date</th>
              <td>{shortDate(mapping.baseline_go_live)}</td>
            </tr>
            <tr>
              <th>Current/Forecast Go-Live Date{asOfLabel}</th>
              <td>{shortDate(mapping.current_go_live)}</td>
            </tr>
            <tr>
              <th>Gross Working-Day Shift{asOfLabel}</th>
              <td>{shiftLabel(mapping.gross_working_day_shift ?? mapping.shift_working_days)}</td>
            </tr>
            <tr>
              <th>Holidays/Non-working Days</th>
              <td>{unavailableCount(mapping.holidays)}</td>
            </tr>
            <tr>
              <th>Net Working-Day Shift{asOfLabel}</th>
              <td className="delay-actual">{shiftLabel(net)}</td>
            </tr>
            <tr>
              <th>Attributed Shift</th>
              <td>{shiftLabel(attributed)}</td>
            </tr>
            <tr>
              <th>Unattributed Shift</th>
              <td>{unattributedLabel(unattributed, mapping.unattributed_status)}</td>
            </tr>
          </tbody>
        </table>
        {net != null ? (
          <p className="delay-reconcile">
            Net Working-Day Shift ({net}) = Attributed Shift ({attributed}) + Unattributed Shift (
            {unattributed})
          </p>
        ) : null}
      </div>

      {mapping.unattributed_status === "requires_pm_validation" ? (
        <p className="delay-unattributed" role="status">
          UNATTRIBUTED / REQUIRES PM VALIDATION — {unattributed} working day
          {unattributed === 1 ? "" : "s"} of the Go-Live shift are not explained by Delay or
          Additional tasks on the Go-Live path.
        </p>
      ) : null}

      <div className="delay-attr-grid">
        <AttributionTable title="Phase-wise attribution" buckets={mapping.phase_attribution ?? []} />
        <AttributionTable title="Owner-wise attribution" buckets={mapping.owner_attribution ?? []} />
        <AttributionTable title="Delay vs Additional" buckets={mapping.type_attribution ?? []} />
      </div>

      <div className="delay-table-card">
        <div className="delay-table-head">
          <div className="delay-table-title">
            <span className="wsr-num" aria-hidden="true">
              <span className="material-symbols-outlined">table_rows</span>
            </span>
            <h2>Delay Mapping Register</h2>
          </div>
        </div>
        {rows.length ? (
          <div className="delay-table-wrap">
            <table className="delay-table delay-sheet delay-register">
              <thead>
                <tr>
                  <th>Phase</th>
                  <th>Task</th>
                  <th>Task Type</th>
                  <th>Owner</th>
                  <th>Owner Class</th>
                  <th>Shift Days</th>
                  <th>Reason</th>
                  <th>Baseline Dates</th>
                  <th>Actual/Current Dates</th>
                  <th>Impacted Successors/Milestones</th>
                  <th>Go-Live Impact</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) =>
                  group.rows.map((row, index) => {
                    const days = row.shift_days ?? row.delay_days;
                    const type = row.task_type;
                    return (
                      <tr
                        key={`${group.name}-${row.wbs || row.name}-${index}`}
                        className={type ? `delay-type-${type}` : undefined}
                      >
                        <td>{group.name}</td>
                        <td>{row.name}</td>
                        <td>{type ? type.toUpperCase() : "Unavailable"}</td>
                        <td>{unavailable(row.owner)}</td>
                        <td>{ownerClassLabel(row.owner_class)}</td>
                        <td>{days == null ? "Unavailable" : days}</td>
                        <td>{unavailable(row.primary_reason)}</td>
                        <td>{dateWindow(row.planned_start, row.planned_finish)}</td>
                        <td>{dateWindow(row.revised_start, row.revised_finish)}</td>
                        <td>{impactedLabel(row)}</td>
                        <td>{row.go_live_impact ? row.go_live_impact.toUpperCase() : "Unavailable"}</td>
                      </tr>
                    );
                  }),
                )}
                <tr className="delay-total-row">
                  <td colSpan={5}>Attributed Total</td>
                  <td>
                    <strong>{attributed}</strong>
                  </td>
                  <td colSpan={5} />
                </tr>
                {unattributed > 0 ? (
                  <tr className="delay-unattr-row">
                    <td colSpan={5}>Unattributed Shift</td>
                    <td>
                      <strong>{unattributed}</strong>
                    </td>
                    <td colSpan={5}>UNATTRIBUTED / REQUIRES PM VALIDATION</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="delay-empty-rows">
            No Delay or Additional tasks on the Go-Live path contributing to the shift
          </p>
        )}
      </div>
    </div>
  );
}

function AttributionTable({
  title,
  buckets,
}: {
  title: string;
  buckets: DelayAttributionBucket[];
}) {
  return (
    <div className="delay-attr-card">
      <h3>{title}</h3>
      {buckets.length ? (
        <table className="delay-attr-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Shift Days</th>
              <th>Tasks</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket) => (
              <tr key={bucket.key}>
                <td>{bucket.label}</td>
                <td>{bucket.shift_days}</td>
                <td>{bucket.task_count ?? "Unavailable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">Unavailable</p>
      )}
    </div>
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

function unattributedLabel(
  value: number,
  status: DelayMappingSheet["unattributed_status"],
): string {
  if (status === "requires_pm_validation") {
    return `${value} — UNATTRIBUTED / REQUIRES PM VALIDATION`;
  }
  return shiftLabel(value);
}

function ownerClassLabel(value: DelayMappingRow["owner_class"]): string {
  if (value === "internal") {
    return "INTERNAL";
  }
  if (value === "client") {
    return "CLIENT";
  }
  if (value === "shared") {
    return "SHARED";
  }
  return "UNKNOWN";
}

function dateWindow(start?: string | null, finish?: string | null): string {
  if (!start && !finish) {
    return "Unavailable";
  }
  if (start && finish) {
    return `${shortDate(start)} – ${shortDate(finish)}`;
  }
  return shortDate(start || finish);
}

function impactedLabel(row: DelayMappingRow): string {
  const names = [...(row.impacted_milestones ?? []), ...(row.impacted_successors ?? [])];
  const unique = [...new Set(names.filter(Boolean))];
  return unique.length ? unique.join(", ") : "Unavailable";
}

export function downloadDelayMappingSheet(mapping: DelayMappingSheet, asOf?: string) {
  const rows = mapping.rows ?? [];
  const net = mapping.net_working_day_shift ?? mapping.actual_shift_working_days;
  const attributed = mapping.attributed_shift_days ?? mapping.total_delayed_days ?? 0;
  const unattributed = mapping.unattributed_shift_days ?? 0;
  const summary = [
    ["Baseline Go-Live Date", mapping.baseline_go_live?.slice(0, 10) || ""],
    ["Current/Forecast Go-Live Date", mapping.current_go_live?.slice(0, 10) || ""],
    ["As Of", asOf?.slice(0, 10) || ""],
    [
      "Gross Working-Day Shift",
      String(mapping.gross_working_day_shift ?? mapping.shift_working_days ?? ""),
    ],
    ["Holidays/Non-working Days", mapping.holidays == null ? "" : String(mapping.holidays)],
    ["Net Working-Day Shift", net == null ? "" : String(net)],
    ["Attributed Shift", String(attributed)],
    ["Unattributed Shift", String(unattributed)],
    [
      "Unattributed Status",
      mapping.unattributed_status === "requires_pm_validation"
        ? "UNATTRIBUTED / REQUIRES PM VALIDATION"
        : mapping.unattributed_status || "",
    ],
    [],
    [
      "Phase",
      "Task",
      "Task Type",
      "Owner",
      "Owner Class",
      "Shift Days",
      "Reason",
      "Baseline Start",
      "Baseline Finish",
      "Current Start",
      "Current Finish",
      "Impacted Successors/Milestones",
      "Go-Live Impact",
    ],
  ];
  const body = rows.map((row) => [
    row.parent_name || "",
    row.name,
    row.task_type ? row.task_type.toUpperCase() : "",
    row.owner || "",
    ownerClassLabel(row.owner_class),
    row.shift_days == null && row.delay_days == null ? "" : String(row.shift_days ?? row.delay_days),
    row.primary_reason || "",
    row.planned_start?.slice(0, 10) || "",
    row.planned_finish?.slice(0, 10) || "",
    row.revised_start?.slice(0, 10) || "",
    row.revised_finish?.slice(0, 10) || "",
    impactedLabel(row) === "Unavailable" ? "" : impactedLabel(row),
    row.go_live_impact ? row.go_live_impact.toUpperCase() : "",
  ]);
  const csv = [
    ...summary,
    ...body,
    ["", "Attributed Total", "", "", "", String(attributed), "", "", "", "", "", "", ""],
    [
      "",
      "Unattributed Shift",
      "",
      "",
      "",
      String(unattributed),
      unattributed ? "UNATTRIBUTED / REQUIRES PM VALIDATION" : "",
      "",
      "",
      "",
      "",
      "",
      "",
    ],
  ]
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

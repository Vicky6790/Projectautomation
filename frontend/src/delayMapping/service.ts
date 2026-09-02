import type { DelayMappingRow, DelayMappingSheet } from "../types";
import type { CompareMppResult, DelayMappingItem } from "./types";

export function fromWsrDelayMapping(mapping: DelayMappingSheet): CompareMppResult {
  const rows = (mapping.rows ?? [])
    .map(toLiveItem)
    .filter((row): row is DelayMappingItem => row !== null);
  return {
    rows,
    summary: {
      taskCount: mapping.current_task_count ?? rows.length,
      delayedTaskCount: mapping.delayed_task_count ?? rows.filter((row) => row.taskType === "Delay").length,
      additionalTaskCount:
        mapping.additional_task_count ?? rows.filter((row) => row.taskType === "Additional").length,
      totalShiftDays: mapping.total_delayed_days ?? rows.reduce((sum, row) => sum + (row.delayDays ?? 0), 0),
      baselineGoLive: mapping.baseline_go_live ?? null,
      currentGoLive: mapping.current_go_live ?? null,
      asOf: mapping.as_of_date ?? null,
      shiftWorkingDays: mapping.shift_working_days ?? mapping.gross_working_day_shift ?? null,
      holidays: mapping.holidays ?? null,
      actualShiftWorkingDays: mapping.actual_shift_working_days ?? mapping.net_working_day_shift ?? null,
    },
    source: "live",
  };
}

export function listedItems(result: CompareMppResult): DelayMappingItem[] {
  return [...result.rows];
}

export function emptyComparison(): CompareMppResult {
  return {
    rows: [],
    summary: {
      taskCount: 0,
      delayedTaskCount: 0,
      additionalTaskCount: 0,
      totalShiftDays: 0,
      baselineGoLive: null,
      currentGoLive: null,
      asOf: null,
      shiftWorkingDays: null,
      holidays: null,
      actualShiftWorkingDays: null,
    },
    source: "live",
  };
}

function toLiveItem(row: DelayMappingRow): DelayMappingItem | null {
  if (row.task_type !== "delay" && row.task_type !== "additional") {
    return null;
  }
  return {
    id: String(row.current_task_id ?? row.name),
    taskName: row.name,
    parentName: row.parent_name ?? null,
    plannedFinish: row.planned_finish ?? null,
    actualFinish: row.revised_finish ?? null,
    delayDays: row.shift_days ?? row.delay_days ?? null,
    owner: row.owner ?? null,
    critical: row.critical ?? null,
    taskType: row.task_type === "additional" ? "Additional" : "Delay",
    evidence: row.evidence_reason || "",
    predecessorNames: row.predecessor_names ?? [],
  };
}

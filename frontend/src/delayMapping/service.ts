import type { DelayMappingRow, DelayMappingSheet } from "../types";
import type {
  CompareMppResult,
  DelayMappingItem,
  DelayMappingSummary,
  GoLiveImpact,
  MppTaskSnapshot,
} from "./types";

const WEEKEND = new Set([0, 6]);

export function workingDaysBetween(
  fromIso: string | null | undefined,
  toIso: string | null | undefined,
  holidays: Set<string> = new Set(),
): number | null {
  const start = parseIso(fromIso);
  const end = parseIso(toIso);
  if (!start || !end) {
    return null;
  }
  if (end <= start) {
    return 0;
  }
  let count = 0;
  const cursor = new Date(start);
  cursor.setDate(cursor.getDate() + 1);
  while (cursor <= end) {
    const key = iso(cursor);
    if (!WEEKEND.has(cursor.getDay()) && !holidays.has(key)) {
      count += 1;
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  return count;
}

export function classifyExistingTask(
  baselineFinish: string | null,
  currentFinish: string | null,
  holidays?: Set<string>,
): { taskType: "DELAYED" | null; shiftDays: number | null; baselineUnavailable: boolean } {
  if (!baselineFinish) {
    return { taskType: null, shiftDays: null, baselineUnavailable: true };
  }
  if (!currentFinish) {
    return { taskType: null, shiftDays: null, baselineUnavailable: false };
  }
  const shiftDays = workingDaysBetween(baselineFinish, currentFinish, holidays);
  if (shiftDays == null || shiftDays <= 0) {
    return { taskType: null, shiftDays: shiftDays ?? 0, baselineUnavailable: false };
  }
  return { taskType: "DELAYED", shiftDays, baselineUnavailable: false };
}

export function compareMPP(_input?: {
  baselineMPP?: MppTaskSnapshot[] | null;
  currentMPP?: MppTaskSnapshot[] | null;
}): CompareMppResult {
  return mockComparison();
}

export function fromWsrDelayMapping(mapping: DelayMappingSheet): CompareMppResult {
  const items = (mapping.rows ?? []).map((row) => toLiveItem(row, mapping));
  const additionalTasks = items;
  const totalShift = mapping.actual_shift_working_days ?? mapping.net_working_day_shift ?? null;
  const goLiveImpact: GoLiveImpact = {
    baselineGoLive: mapping.baseline_go_live ?? null,
    currentGoLive: mapping.current_go_live ?? null,
    totalShift,
  };
  const summary: DelayMappingSummary = {
    baselineGoLive: mapping.baseline_go_live ?? null,
    currentGoLive: mapping.current_go_live ?? null,
    goLiveShift: totalShift,
    delayedTaskCount: 0,
    additionalTaskCount: additionalTasks.length,
    tasksRead: mapping.current_task_count ?? 0,
    baselineFinishNaCount: mapping.additional_task_count ?? additionalTasks.length,
    delaySheetRows: additionalTasks.length,
    holidays: mapping.holidays ?? null,
    calendarNote: null,
    validationWarning: mapping.reconciliation_warning ?? null,
  };
  return {
    delayedTasks: [],
    additionalTasks,
    unchangedTasks: [],
    goLiveImpact,
    summary,
    source: "live",
  };
}

export function listedItems(result: CompareMppResult): DelayMappingItem[] {
  return [...result.delayedTasks, ...result.additionalTasks].sort((left, right) => {
    const finish = (left.currentFinish || "").localeCompare(right.currentFinish || "");
    if (finish !== 0) {
      return finish;
    }
    return left.taskName.localeCompare(right.taskName);
  });
}

export function emptyComparison(): CompareMppResult {
  return {
    delayedTasks: [],
    additionalTasks: [],
    unchangedTasks: [],
    goLiveImpact: {
      baselineGoLive: null,
      currentGoLive: null,
      totalShift: null,
    },
    summary: {
      baselineGoLive: null,
      currentGoLive: null,
      goLiveShift: null,
      delayedTaskCount: 0,
      additionalTaskCount: 0,
      tasksRead: 0,
      baselineFinishNaCount: 0,
      delaySheetRows: 0,
      holidays: null,
      calendarNote: null,
      validationWarning: null,
    },
    source: "live",
  };
}

export function contributingItems(result: CompareMppResult): DelayMappingItem[] {
  return listedItems(result)
    .filter((item) => item.goLiveImpact > 0)
    .sort((a, b) => b.goLiveImpact - a.goLiveImpact || a.taskName.localeCompare(b.taskName));
}

function mockComparison(): CompareMppResult {
  const holidays = new Set<string>();
  const delayedTasks: DelayMappingItem[] = [
    item({
      id: "ia-feedback",
      taskName: "IA Feedback Delay",
      phase: "UX",
      taskType: "DELAYED",
      baselineFinish: "2026-08-10",
      currentFinish: "2026-08-13",
      owner: "Client",
      goLiveImpact: 3,
      predecessors: ["IA Creation"],
      successors: ["UX Approval"],
      holidays,
    }),
    item({
      id: "ui-approval",
      taskName: "UI Approval Delay",
      phase: "UI",
      taskType: "DELAYED",
      baselineFinish: "2026-08-20",
      currentFinish: "2026-08-24",
      owner: "Client",
      goLiveImpact: 2,
      predecessors: ["UI Creation"],
      successors: ["HTML"],
      holidays,
    }),
    item({
      id: "cms-integration",
      taskName: "CMS Integration",
      phase: "CMS",
      taskType: "DELAYED",
      baselineFinish: "2026-08-18",
      currentFinish: "2026-08-25",
      owner: "Idealake",
      goLiveImpact: 0,
      predecessors: ["Backend API"],
      successors: ["QA Cycle"],
      holidays,
    }),
  ];
  const additionalTasks: DelayMappingItem[] = [
    item({
      id: "ux-research",
      taskName: "Additional UX Research",
      phase: "UX",
      taskType: "ADDITIONAL",
      baselineFinish: null,
      currentStart: "2026-08-12",
      currentFinish: "2026-08-16",
      owner: "Idealake",
      goLiveImpact: 2,
      predecessors: ["Wireframe"],
      successors: ["UX Approval"],
      holidays,
    }),
    item({
      id: "qa-review",
      taskName: "Additional QA Review",
      phase: "QA",
      taskType: "ADDITIONAL",
      baselineFinish: null,
      currentStart: "2026-09-28",
      currentFinish: "2026-09-29",
      owner: "Idealake",
      goLiveImpact: 1,
      predecessors: ["QA Cycle"],
      successors: ["UAT"],
      holidays,
    }),
    item({
      id: "design-spike",
      taskName: "Parallel design spike",
      phase: "UX",
      taskType: "ADDITIONAL",
      baselineFinish: null,
      currentStart: "2026-08-03",
      currentFinish: "2026-08-06",
      owner: "Idealake",
      goLiveImpact: 0,
      predecessors: [],
      successors: [],
      holidays,
    }),
  ];
  const goLiveShift = workingDaysBetween("2026-09-30", "2026-10-12") ?? 0;
  return {
    delayedTasks,
    additionalTasks,
    unchangedTasks: [],
    goLiveImpact: {
      baselineGoLive: "2026-09-30",
      currentGoLive: "2026-10-12",
      totalShift: goLiveShift,
    },
    summary: {
      baselineGoLive: "2026-09-30",
      currentGoLive: "2026-10-12",
      goLiveShift,
      delayedTaskCount: delayedTasks.length,
      additionalTaskCount: additionalTasks.length,
      tasksRead: delayedTasks.length + additionalTasks.length,
      baselineFinishNaCount: additionalTasks.length,
      delaySheetRows: additionalTasks.length,
      holidays: null,
      calendarNote: null,
      validationWarning: null,
    },
    source: "sample",
  };
}

function item(input: {
  id: string;
  taskName: string;
  phase: string;
  taskType: "DELAYED" | "ADDITIONAL";
  baselineFinish: string | null;
  currentStart?: string | null;
  currentFinish: string | null;
  owner: string | null;
  goLiveImpact: number;
  predecessors: string[];
  successors: string[];
  holidays: Set<string>;
}): DelayMappingItem {
  const isAdditional = input.taskType === "ADDITIONAL";
  const classified = isAdditional
    ? { shiftDays: null as number | null, baselineUnavailable: true }
    : classifyExistingTask(input.baselineFinish, input.currentFinish, input.holidays);
  const shiftDays = isAdditional ? null : classified.shiftDays;
  return {
    id: input.id,
    taskId: input.id,
    taskName: input.taskName,
    wbs: null,
    phase: input.phase,
    taskType: input.taskType,
    baselineFinish: input.baselineFinish,
    currentStart: input.currentStart ?? null,
    currentFinish: input.currentFinish,
    shiftDays,
    owner: input.owner,
    isAdditional,
    goLiveImpact: input.goLiveImpact,
    predecessors: input.predecessors,
    successors: input.successors,
    matchStatus: isAdditional ? "ADDITIONAL" : "MATCHED",
    calculationStatus: "CALCULATED",
    baselineUnavailable: classified.baselineUnavailable,
    evidence: isAdditional
      ? "Additional task contributes to the dependency chain ending at Go-Live."
      : delayEvidence(input.baselineFinish, input.currentFinish, shiftDays),
  };
}

function toLiveItem(row: DelayMappingRow, mapping: DelayMappingSheet): DelayMappingItem {
  const isAdditional = row.task_type === "additional";
  const shiftDays = isAdditional ? null : (row.shift_days ?? row.delay_days ?? null);
  const goLiveImpact = row.go_live_impact_days ?? 0;
  return {
    id: String(row.current_task_id ?? `${row.wbs || ""}-${row.name}`),
    taskId: String(row.current_task_id ?? ""),
    taskName: row.name,
    wbs: row.wbs ?? row.outline_number ?? null,
    phase: row.parent_name?.trim() || "Other",
    taskType: isAdditional ? "ADDITIONAL" : "DELAYED",
    baselineFinish: row.planned_finish ?? null,
    currentStart: row.revised_start ?? null,
    currentFinish: row.revised_finish ?? null,
    shiftDays,
    owner: row.owner ?? null,
    isAdditional,
    goLiveImpact,
    predecessors: row.predecessor_names ?? [],
    successors: row.successor_names ?? row.impacted_successors ?? [],
    matchStatus: row.match_status ?? (isAdditional ? "additional" : "matched"),
    calculationStatus: row.calculation_status ?? "calculated",
    baselineUnavailable: isAdditional && !row.planned_finish,
    evidence:
      row.evidence_reason
      || (isAdditional
        ? "Additional task contributes to the dependency chain ending at Go-Live."
        : delayEvidence(row.planned_finish, row.revised_finish, shiftDays, mapping.holidays)),
  };
}

function delayEvidence(
  baselineFinish: string | null | undefined,
  currentFinish: string | null | undefined,
  shiftDays: number | null,
  holidays?: number | null,
): string {
  if (!baselineFinish || !currentFinish || shiftDays == null) {
    return "Required finish dates are unavailable.";
  }
  const holidayNote =
    holidays && holidays > 0 ? ` Project holidays in the Go-Live span: ${holidays}.` : "";
  return `Current Finish is later than Baseline Finish. Working-day variance: ${shiftDays}.${holidayNote}`;
}

function parseIso(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function iso(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

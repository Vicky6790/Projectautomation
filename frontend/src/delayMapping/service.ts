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
): { taskType: "Delay" | null; shiftDays: number | null; baselineUnavailable: boolean } {
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
  return { taskType: "Delay", shiftDays, baselineUnavailable: false };
}

export function compareMPP(_input?: {
  baselineMPP?: MppTaskSnapshot[] | null;
  currentMPP?: MppTaskSnapshot[] | null;
}): CompareMppResult {
  return mockComparison();
}

export function fromWsrDelayMapping(mapping: DelayMappingSheet): CompareMppResult {
  const items = (mapping.rows ?? [])
    .filter((row) => row.task_type === "delay" || row.task_type === "additional")
    .map((row) => toLiveItem(row, mapping));
  const delayedTasks = items.filter((item) => item.taskType === "Delay");
  const additionalTasks = items.filter((item) => item.taskType === "Additional");
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
    delayedTaskCount: delayedTasks.length,
    additionalTaskCount: additionalTasks.length,
    holidays: mapping.holidays ?? null,
    calendarNote:
      mapping.calendar_source === "weekdays_fallback"
        ? "Working days use the system weekday calendar (project calendar unavailable)."
        : null,
  };
  return {
    delayedTasks,
    additionalTasks,
    unchangedTasks: [],
    goLiveImpact,
    summary,
    source: "live",
  };
}

export function listedItems(result: CompareMppResult): DelayMappingItem[] {
  return [...result.delayedTasks, ...result.additionalTasks];
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
      holidays: null,
      calendarNote: null,
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
      taskType: "Delay",
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
      taskType: "Delay",
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
      taskType: "Delay",
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
      taskType: "Additional",
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
      taskType: "Additional",
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
      taskType: "Additional",
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
      holidays: null,
      calendarNote: null,
    },
    source: "sample",
  };
}

function item(input: {
  id: string;
  taskName: string;
  phase: string;
  taskType: "Delay" | "Additional";
  baselineFinish: string | null;
  currentStart?: string | null;
  currentFinish: string | null;
  owner: string | null;
  goLiveImpact: number;
  predecessors: string[];
  successors: string[];
  holidays: Set<string>;
}): DelayMappingItem {
  const isAdditional = input.taskType === "Additional";
  const classified = isAdditional
    ? { shiftDays: input.goLiveImpact, baselineUnavailable: false }
    : classifyExistingTask(input.baselineFinish, input.currentFinish, input.holidays);
  const shiftDays = isAdditional ? input.goLiveImpact : classified.shiftDays;
  return {
    id: input.id,
    taskName: input.taskName,
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
    baselineUnavailable: classified.baselineUnavailable,
    evidence: isAdditional
      ? "Task exists in Current MPP but not in Baseline MPP."
      : delayEvidence(input.baselineFinish, input.currentFinish, shiftDays),
  };
}

function toLiveItem(row: DelayMappingRow, mapping: DelayMappingSheet): DelayMappingItem {
  const isAdditional = row.task_type === "additional";
  const shiftDays = row.shift_days ?? row.delay_days ?? null;
  const goLiveImpact = shiftDays && shiftDays > 0 ? shiftDays : 0;
  return {
    id: String(row.current_task_id ?? `${row.wbs || ""}-${row.name}`),
    taskName: row.name,
    phase: row.parent_name?.trim() || "Other",
    taskType: isAdditional ? "Additional" : "Delay",
    baselineFinish: row.planned_finish ?? null,
    currentStart: row.revised_start ?? null,
    currentFinish: row.revised_finish ?? null,
    shiftDays,
    owner: row.owner ?? null,
    isAdditional,
    goLiveImpact,
    predecessors: [],
    successors: row.impacted_successors ?? [],
    baselineUnavailable: isAdditional && !row.planned_finish,
    evidence: isAdditional
      ? "Task exists in Current MPP but not in Baseline MPP."
      : delayEvidence(row.planned_finish, row.revised_finish, shiftDays, mapping.holidays),
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

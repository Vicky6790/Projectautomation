export type DelayTaskType = "Delay" | "Additional";

export type DelayMappingItem = {
  id: string;
  taskName: string;
  parentName: string | null;
  plannedFinish: string | null;
  actualFinish: string | null;
  delayDays: number | null;
  owner: string | null;
  critical: boolean | null;
  taskType: DelayTaskType;
  evidence: string;
  predecessorNames: string[];
};

export type DelayMappingSummary = {
  taskCount: number;
  delayedTaskCount: number;
  additionalTaskCount: number;
  totalShiftDays: number;
  baselineGoLive: string | null;
  currentGoLive: string | null;
  asOf: string | null;
  shiftWorkingDays: number | null;
  holidays: number | null;
  actualShiftWorkingDays: number | null;
};

export type CompareMppResult = {
  rows: DelayMappingItem[];
  summary: DelayMappingSummary;
  source: "live";
};

export type DelayTaskType = "Delay" | "Additional";

export type DelayMappingItem = {
  id: string;
  taskName: string;
  phase: string;
  taskType: DelayTaskType;
  baselineFinish: string | null;
  currentStart: string | null;
  currentFinish: string | null;
  shiftDays: number | null;
  owner: string | null;
  isAdditional: boolean;
  goLiveImpact: number;
  matchStatus?: string | null;
  calculationStatus?: string | null;
  predecessors: string[];
  successors: string[];
  evidence: string;
  baselineUnavailable?: boolean;
};

export type GoLiveImpact = {
  baselineGoLive: string | null;
  currentGoLive: string | null;
  totalShift: number | null;
};

export type DelayMappingSummary = {
  baselineGoLive: string | null;
  currentGoLive: string | null;
  goLiveShift: number | null;
  delayedTaskCount: number;
  additionalTaskCount: number;
  holidays: number | null;
  calendarNote: string | null;
  validationWarning: string | null;
};

export type CompareMppResult = {
  delayedTasks: DelayMappingItem[];
  additionalTasks: DelayMappingItem[];
  unchangedTasks: DelayMappingItem[];
  goLiveImpact: GoLiveImpact;
  summary: DelayMappingSummary;
  source: "sample" | "live";
};

export type MppTaskSnapshot = {
  id: string;
  name: string;
  outlineNumber?: string | null;
  outlineLevel?: number | null;
  parentPath?: string | null;
  baselineFinish?: string | null;
  start?: string | null;
  finish?: string | null;
  resourceNames?: string[];
  predecessorNames?: string[];
  successorNames?: string[];
  isSummary?: boolean;
  isMilestone?: boolean;
};

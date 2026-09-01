export type Module = "sow" | "wsr" | "retrospective" | "plan";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type ApiError = {
  code: string;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
};

export type LibraryDeliverable = {
  id: string;
  name: string;
  set_based: boolean;
};

export type LibraryPhase = {
  id: string;
  name: string;
  deliverables: LibraryDeliverable[];
};

export type PlanLibrary = {
  phases: LibraryPhase[];
  set_deliverables: string[];
  brand_guideline_modes: string[];
  phase_sequence: [string, string][];
};

export type PhaseSelection = {
  phase_id: string;
  deliverables: string[];
  set_overrides: Record<string, number>;
};

export type PlanConfiguration = {
  name: string;
  common_set_count: number;
  phases: PhaseSelection[];
};

export type GeneratedTask = {
  id: number;
  name: string;
  outline_level: number;
  is_summary: boolean;
  is_milestone: boolean;
  set_name?: string | null;
  predecessor_ids: number[];
};

export type GeneratedPlan = {
  name: string;
  tasks: GeneratedTask[];
};

export type PlanResult = {
  plan?: GeneratedPlan;
  approved?: boolean;
  mpp_available?: boolean;
};

export type EvidenceReference = {
  task_or_milestone_name: string;
  date?: string | null;
  progress?: number | null;
  predecessor_names?: string[] | null;
  resource_assignments?: string[] | null;
  dependency_description?: string | null;
};

export type AiDerivedItem = {
  id: string;
  section: string;
  content: string;
  evidence_references: EvidenceReference[];
  review_status: "pending" | "kept" | "edited" | "removed";
};

export type WsrItemDecision = {
  decision: "kept" | "edited" | "removed";
  content?: string | null;
};

export type WsrEvidenceResponse = {
  item_id: string;
  content: string;
  section: string;
  review_status: AiDerivedItem["review_status"];
  evidence_references: EvidenceReference[];
};

export type NamedDateValue = {
  name: string;
  date?: string | null;
};

export type PhaseStatus = {
  name: string;
  wbs?: string | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  actual_start?: string | null;
  actual_finish?: string | null;
  progress?: number | null;
  state: "not_started" | "in_progress" | "complete";
};

export type DelayAttributionBucket = {
  key: string;
  label: string;
  shift_days: number;
  task_count?: number;
};

export type DelayMappingRow = {
  kind?: "phase" | "task";
  name: string;
  parent_name?: string | null;
  wbs?: string | null;
  task_type?: "delay" | "additional" | "unchanged" | "ahead" | "removed" | "unavailable" | null;
  shift_days?: number | null;
  delay_days?: number | null;
  go_live_impact_days?: number | null;
  owner?: string | null;
  owner_class?: "internal" | "client" | "shared" | "unknown" | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  revised_start?: string | null;
  revised_finish?: string | null;
  primary_reason?: string | null;
  go_live_impact?: "high" | "medium" | null;
  mitigation_plan?: string | null;
  impacted_successors?: string[];
  impacted_milestones?: string[];
  baseline_task_id?: number | null;
  current_task_id?: number | null;
  outline_number?: string | null;
  predecessor_ids?: number[];
  successor_ids?: number[];
  go_live_path_impact?: boolean;
  match_status?: "matched" | "additional" | "removed" | "ambiguous" | null;
  calculation_status?: string | null;
  evidence_reason?: string | null;
  predecessor_names?: string[];
  successor_names?: string[];
  calculation_source?: string | null;
};

export type DelayMappingSheet = {
  baseline_go_live?: string | null;
  current_go_live?: string | null;
  gross_working_day_shift?: number | null;
  shift_working_days?: number | null;
  holidays?: number | null;
  net_working_day_shift?: number | null;
  actual_shift_working_days?: number | null;
  attributed_shift_days?: number;
  unattributed_shift_days?: number;
  unattributed_status?: "explained" | "requires_pm_validation" | null;
  delay_shift_days?: number;
  additional_shift_days?: number;
  total_delayed_days?: number;
  delayed_task_count?: number;
  additional_task_count?: number;
  current_task_count?: number;
  matching_requires_validation?: boolean;
  reconciliation_status?: "reconciled" | "requires_validation" | "unavailable" | null;
  reconciliation_warning?: string | null;
  calendar_source?: "project" | "weekdays_fallback" | null;
  phase_attribution?: DelayAttributionBucket[];
  owner_attribution?: DelayAttributionBucket[];
  type_attribution?: DelayAttributionBucket[];
  rows?: DelayMappingRow[];
};

export type ProgressItem = {
  name: string;
  date?: string | null;
  scheduled_start?: string | null;
  scheduled_finish?: string | null;
  progress?: number | null;
};

export type MilestoneItem = {
  name: string;
  date?: string | null;
  scheduled_start?: string | null;
  scheduled_finish?: string | null;
};

export type ExecutiveHighlight = {
  title: string;
  description: string;
  source_type: "mpp" | "calculation" | "risk-engine";
};

export type ExecutiveFocusItem = {
  title: string;
  description: string;
};

export type ExecutiveRiskItem = {
  title: string;
  description: string;
  severity: "critical" | "high" | "medium" | "low";
};

export type ExecutiveAction = {
  action: string;
  reason: string;
  source_type: "ai-recommendation";
};

export type ExecutiveSummary = {
  summary: string;
  highlights: ExecutiveHighlight[];
  current_focus: ExecutiveFocusItem[];
  executive_risks: ExecutiveRiskItem[];
  recommended_actions: ExecutiveAction[];
};

export type WsrPlanFacts = {
  project_name?: string | null;
  project_owner?: string | null;
  as_of_date?: string;
  generated_at?: string | null;
  project_health?: string | null;
  countdown_days?: number | null;
  overall_progress?: number | null;
  planned_work_items?: number | null;
  completed_work_items?: number | null;
  capacity_utilization?: number | null;
  people_planned?: number | null;
  resources_deployed?: number | null;
  person_days_planned?: number | null;
  phase_count?: number | null;
  last_signed_off_milestone?: NamedDateValue | null;
  next_gate?: NamedDateValue | null;
  planned_go_live_date?: string | null;
  executive_overview?: string | null;
  executive_summary?: ExecutiveSummary | null;
  timeline?: PhaseStatus[] | null;
  phase_statuses?: PhaseStatus[];
  delay_mapping?: DelayMappingSheet | null;
  progress_to_date?: ProgressItem[];
  upcoming_milestones?: MilestoneItem[];
};

export type StatusReport = {
  request_handle?: string | null;
  as_of_date?: string | null;
  generated_at?: string | null;
  planned_only?: boolean;
  exportable?: boolean;
  project_health?: string | null;
  facts?: WsrPlanFacts | null;
  progress: string[];
  milestones: string[];
  client_needs: AiDerivedItem[];
  risks: AiDerivedItem[];
  issues: AiDerivedItem[];
  dependencies: AiDerivedItem[];
  management_attention: AiDerivedItem[];
  decisions_required: AiDerivedItem[];
  next_7_day_priorities: AiDerivedItem[];
};

export type RetrospectiveReport = {
  request_handle?: string | null;
  summary?: string;
  planned_only?: boolean;
  schedule_variance: string[];
  milestone_delivery: string[];
  task_completion: string[];
  what_went_well: string[];
  what_went_poorly: string[];
  lessons_learned: string[];
  recommendations: string[];
};

export type SowFinding = {
  category: string;
  priority?: "high" | "medium" | "low" | null;
  title: string;
  description: string;
  recommendation?: string;
};

export type AnalysisReport = {
  request_handle?: string | null;
  processed_pages?: number | null;
  summary?: string;
  gray_areas: SowFinding[];
  risks: SowFinding[];
  missing_requirements: SowFinding[];
  assumptions: SowFinding[];
  dependencies: SowFinding[];
  clarification_questions: SowFinding[];
};

export type ProcessingResponse = {
  id: string;
  request_handle?: string | null;
  module: Module;
  status: JobStatus;
  file_id: string | null;
  result: AnalysisReport | Record<string, unknown> | null;
  error: ApiError | null;
  created_at: string;
  updated_at: string;
};

export type FileRecord = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  module: Module | null;
  created_at: string;
};

export type HealthResponse = {
  status: string;
  auth_mode: string;
  auth_required: boolean;
};

export type Operator = {
  id: string;
  username: string;
  role: "operator" | "admin";
  enabled: boolean;
};

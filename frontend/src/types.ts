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

export type StatusReport = {
  request_handle?: string | null;
  as_of_date?: string | null;
  generated_at?: string | null;
  planned_only?: boolean;
  exportable?: boolean;
  project_health?: string | null;
  facts?: {
    project_name?: string | null;
    project_owner?: string | null;
    project_health?: string | null;
    generated_at?: string | null;
    planned_go_live_date?: string | null;
    executive_overview?: string | null;
  } | null;
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

export type AnalysisReport = {
  request_handle?: string | null;
  gray_areas: string[];
  risks: string[];
  missing_requirements: string[];
  assumptions: string[];
  dependencies: string[];
  clarification_questions: string[];
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

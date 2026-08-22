export type Module = "sow" | "wsr" | "retrospective" | "plan";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type ApiError = {
  code: string;
  message: string;
  retryable: boolean;
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

import type {
  FileRecord,
  HealthResponse,
  Module,
  PlanConfiguration,
  PlanLibrary,
  ProcessingResponse,
} from "./types";

export class ApiRequestError extends Error {
  code: string;
  retryable: boolean;
  details?: Record<string, unknown>;

  constructor(
    message: string,
    code = "REQUEST_FAILED",
    retryable = false,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | {
          error?: {
            message?: string;
            code?: string;
            retryable?: boolean;
            details?: Record<string, unknown>;
          };
        }
      | null;
    throw new ApiRequestError(
      payload?.error?.message ?? `Request failed: ${response.status}`,
      payload?.error?.code ?? "REQUEST_FAILED",
      Boolean(payload?.error?.retryable),
      payload?.error?.details,
    );
  }
  return response.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function uploadFile(file: File, module?: Module): Promise<FileRecord> {
  const body = new FormData();
  body.append("file", file);
  if (module) {
    body.append("module", module);
  }
  return request<FileRecord>("/api/v1/files", { method: "POST", body });
}

export function startJob(module: Module, fileId: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/${module}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_id: fileId }),
  });
}

export function getJob(module: Module, jobId: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/${module}/jobs/${jobId}`);
}

export function retryJob(module: Module, jobId: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/${module}/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export function uploadSow(file: File): Promise<FileRecord> {
  const body = new FormData();
  body.append("file", file);
  return request<FileRecord>("/api/v1/sow/uploads", { method: "POST", body });
}

export function analyzeSow(handle: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/sow/requests/${handle}/analyze`, {
    method: "POST",
  });
}

export function getSowRequest(handle: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/sow/requests/${handle}`);
}

export async function downloadSowReport(handle: string): Promise<Blob> {
  const response = await fetch(`/api/v1/sow/requests/${handle}/report`);
  if (!response.ok) {
    throw new ApiRequestError("Report download failed");
  }
  return response.blob();
}

export function uploadFileWithProgress(
  file: File,
  onProgress: (percent: number) => void,
): { promise: Promise<FileRecord>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<FileRecord>((resolve, reject) => {
    xhr.open("POST", "/api/v1/sow/uploads");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      try {
        const payload = JSON.parse(xhr.responseText) as FileRecord & {
          error?: { message?: string; code?: string; retryable?: boolean };
        };
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload);
          return;
        }
        reject(
          new ApiRequestError(
            payload.error?.message ?? `Upload failed: ${xhr.status}`,
            payload.error?.code,
            Boolean(payload.error?.retryable),
          ),
        );
      } catch (error) {
        reject(error instanceof Error ? error : new ApiRequestError("Upload failed"));
      }
    };
    xhr.onerror = () => reject(new ApiRequestError("Upload failed"));
    xhr.onabort = () => reject(new ApiRequestError("Upload cancelled", "UPLOAD_CANCELLED"));
    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
  });
  return { promise, abort: () => xhr.abort() };
}

export function getPlanLibrary(): Promise<PlanLibrary> {
  return request<PlanLibrary>("/api/v1/plan/library");
}

export function previewPlan(config: PlanConfiguration): Promise<ProcessingResponse> {
  return request<ProcessingResponse>("/api/v1/plan/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function retryPlanPreview(handle: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/plan/requests/${handle}/preview`, {
    method: "POST",
  });
}

export function getPlanRequest(handle: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/plan/requests/${handle}`);
}

export function approvePlan(handle: string): Promise<ProcessingResponse> {
  return request<ProcessingResponse>(`/api/v1/plan/requests/${handle}/approve`, {
    method: "POST",
  });
}

export async function downloadPlanMpp(handle: string): Promise<Blob> {
  const response = await fetch(`/api/v1/plan/requests/${handle}/mpp`);
  if (!response.ok) {
    throw new ApiRequestError("Plan file download failed");
  }
  return response.blob();
}

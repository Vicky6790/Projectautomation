import type { FileRecord, HealthResponse, Module, ProcessingResponse } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null;
    throw new Error(payload?.error?.message ?? `Request failed: ${response.status}`);
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

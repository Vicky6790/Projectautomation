import type { FileRecord, ProcessingResponse, StatusReport } from "./types";

const WSR_SESSION_KEY = "pa-wsr-session";

type StoredWsrSession = {
  handle: string;
  filename: string;
};

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function saveWsrSession(handle: string, filename: string): void {
  const payload: StoredWsrSession = { handle, filename };
  storage()?.setItem(WSR_SESSION_KEY, JSON.stringify(payload));
}

export function readWsrSession(): StoredWsrSession | null {
  const store = storage();
  if (!store) {
    return null;
  }
  let raw = store.getItem(WSR_SESSION_KEY);
  if (!raw) {
    try {
      raw = window.sessionStorage.getItem(WSR_SESSION_KEY);
      if (raw) {
        store.setItem(WSR_SESSION_KEY, raw);
        window.sessionStorage.removeItem(WSR_SESSION_KEY);
      }
    } catch {
      raw = null;
    }
  }
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as StoredWsrSession;
    if (!parsed?.handle) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearWsrSession(): void {
  storage()?.removeItem(WSR_SESSION_KEY);
}

export function restoredUpload(session: StoredWsrSession): FileRecord {
  return {
    id: session.handle,
    filename: session.filename,
    content_type: "application/vnd.ms-project",
    size: 0,
    module: "wsr",
    created_at: "",
  };
}

export function asWsrReport(result: ProcessingResponse["result"]): StatusReport | null {
  if (!result || typeof result !== "object") {
    return null;
  }
  const data = result as StatusReport;
  return {
    as_of_date: data.as_of_date ?? null,
    generated_at: data.generated_at ?? null,
    planned_only: Boolean(data.planned_only),
    exportable: Boolean(data.exportable),
    project_health: data.project_health ?? data.facts?.project_health ?? null,
    facts: data.facts ?? null,
    progress: data.progress ?? [],
    milestones: data.milestones ?? [],
    client_needs: data.client_needs ?? [],
    risks: data.risks ?? [],
    issues: data.issues ?? [],
    dependencies: data.dependencies ?? [],
    management_attention: data.management_attention ?? [],
    decisions_required: data.decisions_required ?? [],
    next_7_day_priorities: data.next_7_day_priorities ?? [],
  };
}

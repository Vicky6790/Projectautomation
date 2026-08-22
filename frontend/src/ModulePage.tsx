import { useState } from "react";
import { getJob, retryJob, startJob, uploadFile } from "./api";
import type { Module, ProcessingResponse } from "./types";

type Props = {
  module: Module;
  title: string;
};

export function ModulePage({ module, title }: Props) {
  const [job, setJob] = useState<ProcessingResponse | null>(null);
  const [message, setMessage] = useState(
    "Upload a file to start a job. Processing itself lands in later work orders.",
  );
  const [busy, setBusy] = useState(false);

  async function onUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setBusy(true);
    try {
      const uploaded = await uploadFile(file, module);
      const started = await startJob(module, uploaded.id);
      setJob(started);
      setMessage(`Queued job ${started.id} for ${uploaded.filename}`);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    if (!job) {
      return;
    }
    setBusy(true);
    try {
      setJob(await getJob(module, job.id));
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Status failed");
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!job) {
      return;
    }
    setBusy(true);
    try {
      setJob(await retryJob(module, job.id));
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>{title}</h2>
      <p>{message}</p>
      <label className="upload">
        Choose file
        <input type="file" onChange={onUpload} disabled={busy} />
      </label>
      {job ? (
        <div className="job">
          <p>
            <strong>Job</strong> {job.id}
          </p>
          <p>
            <strong>Status</strong> {job.status}
          </p>
          <button type="button" onClick={() => void refresh()} disabled={busy}>
            Refresh status
          </button>
          <button type="button" onClick={() => void retry()} disabled={busy}>
            Retry
          </button>
        </div>
      ) : null}
    </section>
  );
}

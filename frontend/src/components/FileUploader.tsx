import { useRef, useState, type ChangeEvent } from "react";
import { uploadFileWithProgress, type UploadProgress } from "../api";
import type { FileRecord } from "../types";

type Props = {
  disabled?: boolean;
  accept?: string;
  label?: string;
  hint?: string;
  endpoint?: string;
  variant?: "default" | "button" | "card";
  onUploaded: (file: FileRecord) => void;
  onError: (message: string) => void;
  onProgress?: (update: UploadProgress | null) => void;
};

export function FileUploader({
  disabled,
  accept = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  label = "Choose SOW (PDF or Word)",
  hint,
  endpoint = "/api/v1/sow/uploads",
  variant = "default",
  onUploaded,
  onError,
  onProgress,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);

  function report(update: UploadProgress | null) {
    setProgress(update);
    onProgress?.(update);
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const { promise, abort } = uploadFileWithProgress(file, (update) => report(update), endpoint);
    abortRef.current = abort;
    report({ percent: 0, phase: "uploading" });
    void promise
      .then(onUploaded)
      .catch((error: unknown) => {
        onError(error instanceof Error ? error.message : "Upload failed");
      })
      .finally(() => {
        abortRef.current = null;
        report(null);
        if (inputRef.current) {
          inputRef.current.value = "";
        }
      });
  }

  const busy = disabled || progress !== null;
  const input = (
    <input
      ref={inputRef}
      className={variant === "button" || variant === "card" ? "sr-only" : undefined}
      type="file"
      accept={accept}
      onChange={chooseFile}
      disabled={busy}
    />
  );

  return (
    <div className={`uploader${variant === "button" || variant === "card" ? " uploader-button" : ""}`}>
      {variant === "card" ? (
        <button
          type="button"
          className="wsr-upload-trigger"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          <span className="wsr-upload-icon" aria-hidden="true">
            <span className="material-symbols-outlined">upload_file</span>
          </span>
          <span>
            <span className="wsr-upload-title">{label}</span>
            <span className="wsr-upload-hint">{hint ?? "Microsoft Project (.mpp)"}</span>
          </span>
        </button>
      ) : variant === "button" ? (
        <button
          type="button"
          className="btn btn-outline"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {label}
        </button>
      ) : (
        <label className="upload">
          {label}
          {input}
        </label>
      )}
      {variant === "button" || variant === "card" ? input : null}
      {progress !== null ? (
        <div className="upload-progress" role="status" aria-live="polite">
          <div className="upload-progress-track">
            <span
              className={progress.phase === "processing" ? "is-processing" : undefined}
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <p>
            {progress.phase === "processing"
              ? "Preparing file…"
              : `Uploading ${progress.percent}%`}
          </p>
          <button type="button" onClick={() => abortRef.current?.()}>
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}

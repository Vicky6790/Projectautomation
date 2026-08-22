import { useRef, useState, type ChangeEvent } from "react";
import { uploadFileWithProgress } from "../api";
import type { FileRecord } from "../types";

type Props = {
  disabled?: boolean;
  onUploaded: (file: FileRecord) => void;
  onError: (message: string) => void;
};

export function FileUploader({ disabled, onUploaded, onError }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const [progress, setProgress] = useState<number | null>(null);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const { promise, abort } = uploadFileWithProgress(file, setProgress);
    abortRef.current = abort;
    setProgress(0);
    void promise
      .then(onUploaded)
      .catch((error: unknown) => {
        onError(error instanceof Error ? error.message : "Upload failed");
      })
      .finally(() => {
        abortRef.current = null;
        setProgress(null);
        if (inputRef.current) {
          inputRef.current.value = "";
        }
      });
  }

  return (
    <div className="uploader">
      <label className="upload">
        Choose SOW (PDF or Word)
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={chooseFile}
          disabled={disabled || progress !== null}
        />
      </label>
      {progress !== null ? (
        <div className="progress">
          <p>Uploading {progress}%</p>
          <button type="button" onClick={() => abortRef.current?.()}>
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}

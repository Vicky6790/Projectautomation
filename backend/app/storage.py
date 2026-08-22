from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.errors import AppError
from app.models import FileRecord, JobStatus, Module, ProcessingResponse


def _now() -> datetime:
    return datetime.now(UTC)


class LocalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.data_dir)
        self.uploads = self.root / "uploads"
        self.jobs = self.root / "jobs"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.jobs.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        module: Module | None,
        extracted_text: str | None = None,
    ) -> FileRecord:
        file_id = str(uuid.uuid4())
        dest = self.uploads / file_id
        dest.write_bytes(content)
        if extracted_text is not None:
            (self.uploads / f"{file_id}.txt").write_text(extracted_text, encoding="utf-8")
        record = FileRecord(
            id=file_id,
            filename=filename,
            content_type=content_type,
            size=len(content),
            module=module,
            extracted_text_available=extracted_text is not None,
            extracted_char_count=len(extracted_text) if extracted_text is not None else None,
            created_at=_now(),
        )
        (self.uploads / f"{file_id}.json").write_text(record.model_dump_json(), encoding="utf-8")
        return record

    def get_file(self, file_id: str) -> tuple[FileRecord, Path]:
        meta = self.uploads / f"{file_id}.json"
        blob = self.uploads / file_id
        if not meta.exists() or not blob.exists():
            raise AppError(404, "FILE_NOT_FOUND", f"File {file_id} was not found")
        record = FileRecord.model_validate_json(meta.read_text(encoding="utf-8"))
        return record, blob

    def create_job(self, module: Module, file_id: str) -> ProcessingResponse:
        self.get_file(file_id)
        now = _now()
        job = ProcessingResponse(
            id=str(uuid.uuid4()),
            module=module,
            status="queued",
            file_id=file_id,
            created_at=now,
            updated_at=now,
        )
        self._write_job(job)
        return job

    def get_job(self, job_id: str) -> ProcessingResponse:
        path = self.jobs / f"{job_id}.json"
        if not path.exists():
            raise AppError(404, "JOB_NOT_FOUND", f"Job {job_id} was not found")
        return ProcessingResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def retry_job(self, job_id: str) -> ProcessingResponse:
        job = self.get_job(job_id)
        if job.status != "failed":
            raise AppError(
                409,
                "RETRY_NOT_ALLOWED",
                "Only failed jobs can be retried",
                retryable=False,
            )
        job.status = "queued"
        job.error = None
        job.result = None
        job.updated_at = _now()
        self._write_job(job)
        return job

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        result: dict | None = None,
        error: dict | None = None,
    ) -> ProcessingResponse:
        job = self.get_job(job_id)
        job.status = status
        job.result = result
        if error is not None:
            from app.models import ApiError

            job.error = ApiError.model_validate(error)
        job.updated_at = _now()
        self._write_job(job)
        return job

    def _write_job(self, job: ProcessingResponse) -> None:
        path = self.jobs / f"{job.id}.json"
        path.write_text(job.model_dump_json(), encoding="utf-8")


store = LocalStore()

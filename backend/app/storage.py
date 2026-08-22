from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import settings
from app.errors import AppError
from app.models import ApiError, FileRecord, JobStatus, Module, ProcessingResponse, ProjectPlanData


def _now() -> datetime:
    return datetime.now(UTC)


class LocalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.data_dir)
        self.requests = self.root / "requests"
        self.requests.mkdir(parents=True, exist_ok=True)

    def _dir(self, handle: str) -> Path:
        return self.requests / handle

    def extracted_text_path(self, handle: str) -> Path:
        return self._dir(handle) / "extracted.txt"

    def report_path(self, handle: str) -> Path:
        return self._dir(handle) / "report.md"

    def plan_path(self, handle: str) -> Path:
        return self._dir(handle) / "plan.json"

    def generated_plan_path(self, handle: str) -> Path:
        return self._dir(handle) / "generated-plan.xml"

    def save_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        module: Module | None,
        extracted_text: str | None = None,
        plan_data: dict | None = None,
    ) -> FileRecord:
        self.purge_expired()
        handle = str(uuid.uuid4())
        path = self._dir(handle)
        path.mkdir(parents=True, exist_ok=True)
        (path / "input.bin").write_bytes(content)
        if extracted_text is not None:
            self.extracted_text_path(handle).write_text(extracted_text, encoding="utf-8")
        if plan_data is not None:
            self.plan_path(handle).write_text(
                ProjectPlanData.model_validate(plan_data).model_dump_json(),
                encoding="utf-8",
            )
        now = _now()
        record = FileRecord(
            id=handle,
            filename=filename,
            content_type=content_type,
            size=len(content),
            module=module,
            extracted_text_available=extracted_text is not None,
            extracted_char_count=len(extracted_text) if extracted_text is not None else None,
            plan_available=plan_data is not None,
            created_at=now,
            last_accessed_at=now,
        )
        self._write_file(record)
        return record

    def create_plan_handle(self) -> FileRecord:
        self.purge_expired()
        handle = str(uuid.uuid4())
        path = self._dir(handle)
        path.mkdir(parents=True, exist_ok=True)
        now = _now()
        record = FileRecord(
            id=handle,
            filename="",
            content_type="application/json",
            size=0,
            module="plan",
            created_at=now,
            last_accessed_at=now,
        )
        self._write_file(record)
        return record

    def get_plan(self, handle: str) -> ProjectPlanData:
        record, _ = self.get_file(handle)
        path = self.plan_path(handle)
        if not record.plan_available or not path.exists():
            raise AppError(404, "PLAN_NOT_FOUND", "No parsed plan is available for this file")
        return ProjectPlanData.model_validate_json(path.read_text(encoding="utf-8"))

    def save_generated_plan(self, handle: str, content: bytes) -> Path:
        path = self.generated_plan_path(handle)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def get_file(self, handle: str) -> tuple[FileRecord, Path]:
        self.purge_expired()
        path = self._dir(handle)
        meta = path / "meta.json"
        blob = path / "input.bin"
        if not meta.exists():
            raise AppError(404, "FILE_NOT_FOUND", f"File {handle} was not found")
        record = FileRecord.model_validate_json(meta.read_text(encoding="utf-8"))
        record.last_accessed_at = _now()
        self._write_file(record)
        return record, blob if blob.exists() else path

    def create_job(self, module: Module, file_id: str | None) -> ProcessingResponse:
        self.purge_expired()
        if module == "plan" and not file_id:
            handle = self.create_plan_handle().id
        else:
            if not file_id:
                raise AppError(400, "FILE_ID_REQUIRED", "file_id is required for this module")
            record, _ = self.get_file(file_id)
            handle = record.id
            existing = self._read_job(handle)
            if existing:
                if existing.module != module:
                    raise AppError(
                        409,
                        "HANDLE_MODULE_CONFLICT",
                        "Request handle belongs to another module",
                    )
                return existing
        now = _now()
        job = ProcessingResponse(
            id=handle,
            request_handle=handle,
            module=module,
            status="queued",
            file_id=handle,
            created_at=now,
            updated_at=now,
        )
        self._write_job(job)
        return job

    def get_job(self, job_id: str) -> ProcessingResponse:
        self.purge_expired()
        job = self._read_job(job_id)
        if job is None:
            raise AppError(404, "JOB_NOT_FOUND", f"Job {job_id} was not found")
        self._touch_file(job_id)
        return job

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
            job.error = ApiError.model_validate(error)
        job.updated_at = _now()
        self._write_job(job)
        return job

    def purge_expired(self, now: datetime | None = None) -> int:
        cutoff = (now or _now()) - timedelta(hours=settings.request_ttl_hours)
        removed = 0
        if not self.requests.exists():
            return 0
        for path in list(self.requests.iterdir()):
            if not path.is_dir():
                continue
            meta = path / "meta.json"
            if not meta.exists():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
                continue
            record = FileRecord.model_validate_json(meta.read_text(encoding="utf-8"))
            last = record.last_accessed_at or record.created_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if last < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        return removed

    def _read_job(self, handle: str) -> ProcessingResponse | None:
        path = self._dir(handle) / "job.json"
        if not path.exists():
            return None
        return ProcessingResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def _write_job(self, job: ProcessingResponse) -> None:
        job.request_handle = job.id
        path = self._dir(job.id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "job.json").write_text(job.model_dump_json(), encoding="utf-8")

    def _write_file(self, record: FileRecord) -> None:
        path = self._dir(record.id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "meta.json").write_text(record.model_dump_json(), encoding="utf-8")

    def _touch_file(self, handle: str) -> None:
        meta = self._dir(handle) / "meta.json"
        if not meta.exists():
            return
        record = FileRecord.model_validate_json(meta.read_text(encoding="utf-8"))
        record.last_accessed_at = _now()
        self._write_file(record)


store = LocalStore()

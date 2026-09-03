from __future__ import annotations

from app import storage as storage_mod
from app.ai.engine import analyze_sow
from app.errors import AppError
from app.ingestion import count_sow_pages
from app.models import AnalysisReport, FileRecord, ProcessingResponse

_CATEGORIES = (
    "gray_areas",
    "risks",
    "missing_requirements",
    "assumptions",
    "dependencies",
    "clarification_questions",
)


def run_sow_analysis(handle: str, *, force: bool = False) -> ProcessingResponse:
    store = storage_mod.store
    job = store.create_job("sow", handle)
    if job.status == "succeeded" and not force:
        return job
    if job.status == "running":
        return job
    store.set_status(handle, "running")
    try:
        record, blob = store.get_file(handle)
        text_path = store.extracted_text_path(handle)
        if not record.extracted_text_available or not text_path.exists():
            raise AppError(
                400,
                "SOW_TEXT_MISSING",
                "No extractable SOW text is stored for this request",
                retryable=False,
            )
        report = analyze_sow(text_path.read_text(encoding="utf-8"))
        payload = report.model_dump()
        payload["request_handle"] = handle
        for key in _CATEGORIES:
            payload.setdefault(key, [])
            for item in payload[key]:
                if isinstance(item, dict):
                    item["category"] = key
        total = sum(len(payload[key]) for key in _CATEGORIES)
        payload["processed_pages"] = _processed_pages(record, blob)
        if not str(payload.get("summary") or "").strip():
            payload["summary"] = f"{total} findings across six categories."
        AnalysisReport.model_validate(payload)
        return store.set_status(handle, "succeeded", result=payload)
    except AppError as exc:
        store.set_status(
            handle,
            "failed",
            error={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
        )
        return store.get_job(handle)
    except Exception:  # noqa: BLE001 - analysis failures stay on the handle
        store.set_status(
            handle,
            "failed",
            error={
                "code": "SOW_ANALYSIS_FAILED",
                "message": "SOW analysis failed",
                "retryable": True,
            },
        )
        return store.get_job(handle)


def _processed_pages(record: FileRecord, blob) -> int:
    if not getattr(blob, "is_file", lambda: False)():
        return 1
    return count_sow_pages(record.filename, blob.read_bytes())

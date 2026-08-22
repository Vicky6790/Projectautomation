from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app import storage as storage_mod
from app.errors import AppError
from app.ingestion import extract_sow_text, validate_upload
from app.models import FileRecord, ProcessingResponse
from app.orchestration.sow import run_sow_analysis
from app.reports import export_report

router = APIRouter(prefix="/api/v1/sow", tags=["sow"])


@router.post("/uploads", response_model=FileRecord)
async def upload_sow(file: UploadFile = File(...)) -> FileRecord:
    filename = file.filename or "upload"
    content = await file.read()
    validate_upload(filename, content, "sow")
    extracted = extract_sow_text(filename, content)
    return storage_mod.store.save_upload(
        filename,
        content,
        file.content_type or "application/octet-stream",
        "sow",
        extracted_text=extracted,
    )


@router.post("/requests/{handle}/analyze", response_model=ProcessingResponse)
def analyze_sow_request(handle: str) -> ProcessingResponse:
    job = run_sow_analysis(handle)
    if job.status == "failed" and job.error:
        raise AppError(
            502 if job.error.retryable else 400,
            job.error.code,
            job.error.message,
            retryable=job.error.retryable,
        )
    return job


@router.get("/requests/{handle}", response_model=ProcessingResponse)
def get_sow_request(handle: str) -> ProcessingResponse:
    return storage_mod.store.get_job(handle)


@router.get("/requests/{handle}/report")
def download_sow_report(handle: str) -> Response:
    job = storage_mod.store.get_job(handle)
    filename, media_type, content = export_report("sow", job)
    storage_mod.store.report_path(job.id).write_bytes(content)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from starlette.requests import Request

from app import storage as storage_mod
from app.errors import AppError
from app.ingestion import validate_upload
from app.models import (
    DelayMappingCompareRequest,
    DelayMappingSheet,
    FileRecord,
    ProcessingResponse,
    WsrEvidenceResponse,
    WsrItemDecision,
)
from app.mpp import read_mpp_bytes
from app.orchestration.wsr import run_wsr_generation
from app.reports import export_report
from app.wsr.review import item_evidence, review_item

router = APIRouter(prefix="/api/v1/wsr", tags=["wsr"])


@router.post("/uploads", response_model=FileRecord)
async def upload_wsr(file: UploadFile = File(...)) -> FileRecord:
    filename = file.filename or "upload"
    content = await file.read()
    validate_upload(filename, content, "wsr")
    plan = read_mpp_bytes(content, filename)
    return storage_mod.store.save_upload(
        filename,
        content,
        file.content_type or "application/octet-stream",
        "wsr",
        plan_data=plan.model_dump(),
    )


@router.post("/delay-mapping", response_model=DelayMappingSheet)
def compare_delay_mapping(body: DelayMappingCompareRequest) -> DelayMappingSheet:
    current_id = body.current_file_id.strip()
    if not current_id:
        raise AppError(400, "CURRENT_MPP_REQUIRED", "Insert an MPP file.")
    current = storage_mod.store.get_plan(current_id)
    from app.wsr.facts import delay_mapping_from_plans

    return delay_mapping_from_plans(current)


@router.post("/requests/{handle}/generate", response_model=ProcessingResponse)
def generate_wsr_request(handle: str) -> ProcessingResponse:
    job = run_wsr_generation(handle)
    if job.status == "failed" and job.error:
        raise AppError(
            502 if job.error.retryable else 400,
            job.error.code,
            job.error.message,
            retryable=job.error.retryable,
        )
    return job


@router.get("/requests/{handle}", response_model=ProcessingResponse)
def get_wsr_request(handle: str) -> ProcessingResponse:
    return storage_mod.store.get_job(handle)


@router.get("/requests/{handle}/report")
def download_wsr_report(handle: str, request: Request) -> Response:
    job = storage_mod.store.get_job(handle)
    filename, media_type, content = export_report(
        "wsr", job, scope=request.query_params.get("scope")
    )
    storage_mod.store.report_path(job.id).write_bytes(content)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/requests/{handle}/items/{item_id}", response_model=ProcessingResponse)
def review_wsr_item(handle: str, item_id: str, body: WsrItemDecision) -> ProcessingResponse:
    return review_item(handle, item_id, body)


@router.get("/requests/{handle}/items/{item_id}/evidence", response_model=WsrEvidenceResponse)
def get_wsr_item_evidence(handle: str, item_id: str) -> WsrEvidenceResponse:
    return item_evidence(handle, item_id)

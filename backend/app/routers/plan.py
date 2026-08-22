from fastapi import APIRouter
from fastapi.responses import Response

from app import storage as storage_mod
from app.errors import AppError
from app.models import ProcessingResponse
from app.plan.expand import PlanConfiguration
from app.plan.library import catalog
from app.plan.service import approve_plan, preview_plan, retry_preview

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.get("/library")
def get_library() -> dict:
    return catalog()


@router.post("/preview", response_model=ProcessingResponse)
def create_preview(config: PlanConfiguration) -> ProcessingResponse:
    return preview_plan(config)


@router.post("/requests/{handle}/preview", response_model=ProcessingResponse)
def retry_plan_preview(handle: str) -> ProcessingResponse:
    return retry_preview(handle)


@router.get("/requests/{handle}", response_model=ProcessingResponse)
def get_plan_request(handle: str) -> ProcessingResponse:
    return storage_mod.store.get_job(handle)


@router.post("/requests/{handle}/approve", response_model=ProcessingResponse)
def approve_plan_request(handle: str) -> ProcessingResponse:
    return approve_plan(handle)


@router.get("/requests/{handle}/mpp")
def download_plan_mpp(handle: str) -> Response:
    job = storage_mod.store.get_job(handle)
    path = storage_mod.store.generated_plan_path(handle)
    if job.status != "succeeded" or not path.exists():
        raise AppError(409, "MPP_NOT_READY", "Generated plan file is not available yet")
    return Response(
        content=path.read_bytes(),
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="generated-plan.xml"'},
    )

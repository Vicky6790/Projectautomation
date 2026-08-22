from fastapi import APIRouter

from app.errors import AppError
from app.models import Module, ProcessingResponse, StartJobRequest
from app.storage import store

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _module_router(module: Module) -> APIRouter:
    module_router = APIRouter(prefix=f"/{module}/jobs")

    @module_router.post("", response_model=ProcessingResponse)
    def start_job(body: StartJobRequest) -> ProcessingResponse:
        if module != "plan" and not body.file_id:
            raise AppError(400, "FILE_ID_REQUIRED", "file_id is required for this module")
        return store.create_job(module, body.file_id)

    @module_router.get("/{job_id}", response_model=ProcessingResponse)
    def get_job(job_id: str) -> ProcessingResponse:
        return store.get_job(job_id)

    @module_router.post("/{job_id}/retry", response_model=ProcessingResponse)
    def retry_job(job_id: str) -> ProcessingResponse:
        return store.retry_job(job_id)

    return module_router


for _module in ("sow", "wsr", "retrospective", "plan"):
    router.include_router(_module_router(_module))

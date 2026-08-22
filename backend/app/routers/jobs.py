from fastapi import APIRouter
from fastapi.responses import Response

from app.errors import AppError
from app.models import Module, ProcessingResponse, StartJobRequest
from app.reports import export_report
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
        if module == "plan":
            from app.plan.service import retry_plan_job

            return retry_plan_job(job_id)
        queued = store.retry_job(job_id)
        if module == "wsr":
            from app.orchestration.wsr import run_wsr_generation

            return run_wsr_generation(job_id)
        return queued

    @module_router.get("/{job_id}/report")
    def download_report(job_id: str) -> Response:
        job = store.get_job(job_id)
        filename, media_type, content = export_report(module, job)
        store.report_path(job.id).write_bytes(content)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if module == "plan":
        from app.models import GeneratedPlan
        from app.mpp import write_generated_plan

        @module_router.post("/{job_id}/mpp")
        def generate_plan_file(job_id: str, body: GeneratedPlan) -> Response:
            job = store.get_job(job_id)
            content = write_generated_plan(body)
            store.save_generated_plan(job.id, content)
            return Response(
                content=content,
                media_type="application/xml",
                headers={
                    "Content-Disposition": f'attachment; filename="{body.name or "plan"}.xml"'
                },
            )

        @module_router.get("/{job_id}/mpp")
        def download_plan_file(job_id: str) -> Response:
            job = store.get_job(job_id)
            path = store.generated_plan_path(job.id)
            if not path.exists():
                raise AppError(409, "MPP_NOT_READY", "Generated plan file is not available yet")
            return Response(
                content=path.read_bytes(),
                media_type="application/xml",
                headers={"Content-Disposition": 'attachment; filename="generated-plan.xml"'},
            )

    return module_router


def _requests_router(module: Module) -> APIRouter:
    requests_router = APIRouter(prefix=f"/{module}/requests")

    @requests_router.get("/{handle}", response_model=ProcessingResponse)
    def get_request(handle: str) -> ProcessingResponse:
        return store.get_job(handle)

    @requests_router.get("/{handle}/report")
    def download_request_report(handle: str) -> Response:
        job = store.get_job(handle)
        filename, media_type, content = export_report(module, job)
        store.report_path(job.id).write_bytes(content)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return requests_router


for _module in ("sow", "wsr", "retrospective", "plan"):
    router.include_router(_module_router(_module))
    router.include_router(_requests_router(_module))

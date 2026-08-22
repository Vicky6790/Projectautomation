from __future__ import annotations

from app import storage as storage_mod
from app.errors import AppError
from app.models import GeneratedPlan, ProcessingResponse
from app.mpp import write_generated_plan
from app.plan.expand import PlanConfiguration, expand_plan
from app.plan.validate import validate_plan_configuration


def preview_plan(config: PlanConfiguration, handle: str | None = None) -> ProcessingResponse:
    validate_plan_configuration(config)
    store = storage_mod.store
    job = store.create_job("plan", handle)
    store.save_plan_config(job.id, config.model_dump())
    try:
        plan = expand_plan(config)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        store.set_status(
            job.id,
            "failed",
            error={"code": "PREVIEW_FAILED", "message": str(exc), "retryable": True},
        )
        raise AppError(500, "PREVIEW_FAILED", "Preview generation failed", retryable=True) from exc
    return store.set_status(
        job.id,
        "succeeded",
        result={"plan": plan.model_dump(), "approved": False, "mpp_available": False},
    )


def retry_preview(handle: str) -> ProcessingResponse:
    config = PlanConfiguration.model_validate(storage_mod.store.load_plan_config(handle))
    return preview_plan(config, handle)


def approve_plan(handle: str) -> ProcessingResponse:
    store = storage_mod.store
    job = store.get_job(handle)
    plan_data = (job.result or {}).get("plan")
    if not plan_data:
        raise AppError(
            409,
            "PREVIEW_NOT_READY",
            "Approve a completed preview before generating the plan file",
            retryable=False,
        )
    plan = GeneratedPlan.model_validate(plan_data)
    result = {**job.result, "approved": False, "mpp_available": False}
    try:
        content = write_generated_plan(plan)
        store.save_generated_plan(handle, content)
    except AppError as exc:
        store.set_status(
            handle,
            "failed",
            result=result,
            error={"code": exc.code, "message": exc.message, "retryable": True},
        )
        raise AppError(
            exc.status_code,
            exc.code,
            exc.message,
            retryable=True,
            details=exc.details,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        store.set_status(
            handle,
            "failed",
            result=result,
            error={"code": "MPP_WRITE_FAILED", "message": str(exc), "retryable": True},
        )
        raise AppError(500, "MPP_WRITE_FAILED", "MPP generation failed", retryable=True) from exc
    return store.set_status(
        handle,
        "succeeded",
        result={**job.result, "approved": True, "mpp_available": True},
    )


def retry_plan_job(handle: str) -> ProcessingResponse:
    job = storage_mod.store.get_job(handle)
    if job.status != "failed":
        raise AppError(409, "RETRY_NOT_ALLOWED", "Only failed jobs can be retried", retryable=False)
    if job.result and job.result.get("plan"):
        return approve_plan(handle)
    return retry_preview(handle)

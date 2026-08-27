from __future__ import annotations

from app import storage as storage_mod
from app.ai.engine import analyze_wsr
from app.errors import AppError
from app.models import AiDerivedItem, ProcessingResponse, StatusReport
from app.wsr.evidence import STORED_AI_SECTIONS
from app.wsr.facts import derive_wsr_facts, resolve_as_of


def run_wsr_generation(handle: str, *, force: bool = False) -> ProcessingResponse:
    store = storage_mod.store
    job = store.create_job("wsr", handle)
    if job.status == "succeeded" and not force:
        return job
    if job.status == "running":
        return job
    store.set_status(handle, "running")
    try:
        plan = store.get_plan(handle)
        as_of = resolve_as_of(plan)
        facts = derive_wsr_facts(plan, as_of)
        snapshot = plan.model_dump()
        snapshot["as_of_date"] = as_of
        snapshot["facts"] = facts.model_dump()
        grouped = analyze_wsr(snapshot)
        overview = grouped.get("executive_overview")
        if isinstance(overview, str) and overview.strip():
            facts = facts.model_copy(update={"executive_overview": overview.strip()})
        ai_fields = {
            key: [AiDerivedItem.model_validate(item) for item in grouped.get(key) or []]
            for key in STORED_AI_SECTIONS
        }
        report = StatusReport(
            request_handle=handle,
            as_of_date=as_of,
            generated_at=facts.generated_at,
            planned_only=plan.planned_only,
            exportable=True,
            project_health=facts.project_health,
            facts=facts,
            progress=[item.name for item in facts.progress_to_date],
            milestones=[item.name for item in facts.upcoming_milestones],
            **ai_fields,
        )
        return store.set_status(handle, "succeeded", result=report.model_dump())
    except AppError as exc:
        store.set_status(
            handle,
            "failed",
            error={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
        )
        return store.get_job(handle)
    except Exception:  # noqa: BLE001 - generation failures stay on the handle
        store.set_status(
            handle,
            "failed",
            error={
                "code": "WSR_GENERATION_FAILED",
                "message": "WSR generation failed",
                "retryable": True,
            },
        )
        return store.get_job(handle)

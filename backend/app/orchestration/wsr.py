from __future__ import annotations

from app import storage as storage_mod
from app.ai.engine import analyze_wsr
from app.errors import AppError
from app.models import AiDerivedItem, ProcessingResponse, StatusReport
from app.wsr.evidence import STORED_AI_SECTIONS, items_from_situation_risks
from app.wsr.executive import generate_executive_summary
from app.wsr.facts import derive_wsr_facts, wsr_publish_date
from app.wsr.intelligence import build_executive_summary_input


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
        as_of = wsr_publish_date()
        facts = derive_wsr_facts(plan, as_of)
        snapshot = plan.model_dump()
        snapshot["as_of_date"] = as_of
        snapshot["facts"] = facts.model_dump()
        grouped = analyze_wsr(snapshot)
        intelligence = build_executive_summary_input(plan, facts, as_of)
        summary = generate_executive_summary(intelligence)
        facts = facts.model_copy(
            update={
                "executive_summary": summary,
                "executive_overview": summary.summary,
            }
        )
        ai_fields = {
            key: [AiDerivedItem.model_validate(item) for item in grouped.get(key) or []]
            for key in STORED_AI_SECTIONS
        }
        situation_risks = items_from_situation_risks(plan, intelligence.get("risks") or [])
        if situation_risks:
            ai_fields["risks"] = situation_risks
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

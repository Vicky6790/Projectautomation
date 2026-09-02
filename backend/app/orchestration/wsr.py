from __future__ import annotations

from app import storage as storage_mod
from app.ai.engine import analyze_wsr
from app.errors import AppError
from app.models import (
    AiDerivedItem,
    ProcessingResponse,
    ProjectPlanData,
    ProjectWsrDashboard,
    StatusReport,
)
from app.wsr.evidence import STORED_AI_SECTIONS, items_from_situation_risks
from app.wsr.executive import generate_executive_summary
from app.wsr.facts import derive_portfolio_summary, derive_wsr_facts, wsr_publish_date
from app.wsr.intelligence import build_executive_summary_input
from app.wsr.projects import PlanProject, split_plan_projects


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
        split = split_plan_projects(plan)
        boards = [_generate_project_dashboard(item, as_of) for item in split.projects]
        first = boards[0]
        portfolio = None
        if len(boards) > 1:
            portfolio = derive_portfolio_summary(plan, as_of)
            boards = [_without_individual_countdown(board) for board in boards]
            first = boards[0]
        report = StatusReport(
            request_handle=handle,
            as_of_date=as_of,
            generated_at=first.facts.generated_at,
            planned_only=plan.planned_only,
            exportable=True,
            project_health=first.facts.project_health,
            facts=first.facts,
            portfolio_name=(portfolio.name if portfolio else None) or split.portfolio_name,
            portfolio=portfolio,
            projects=boards,
            progress=first.progress,
            milestones=first.milestones,
            client_needs=first.client_needs,
            risks=first.risks,
            issues=first.issues,
            dependencies=first.dependencies,
            management_attention=first.management_attention,
            decisions_required=first.decisions_required,
            next_7_day_priorities=first.next_7_day_priorities,
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


def _generate_project_dashboard(item: PlanProject, as_of: str) -> ProjectWsrDashboard:
    plan: ProjectPlanData = item.plan
    facts = derive_wsr_facts(plan, as_of, project_code=item.code)
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
        key: [AiDerivedItem.model_validate(row) for row in grouped.get(key) or []]
        for key in STORED_AI_SECTIONS
    }
    situation_risks = items_from_situation_risks(plan, intelligence.get("risks") or [])
    if situation_risks:
        ai_fields["risks"] = situation_risks
    return ProjectWsrDashboard(
        project_code=item.code or facts.project_code or "1",
        project_name=facts.project_name,
        facts=facts,
        progress=[row.name for row in facts.progress_to_date],
        milestones=[row.name for row in facts.upcoming_milestones],
        **ai_fields,
    )


def _without_individual_countdown(board: ProjectWsrDashboard) -> ProjectWsrDashboard:
    return board.model_copy(
        update={
            "facts": board.facts.model_copy(update={"countdown_days": None}),
        }
    )

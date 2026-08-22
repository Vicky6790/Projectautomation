from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app import storage as storage_mod
from app.ai.engine import analyze_wsr
from app.errors import AppError
from app.models import ProcessingResponse, ProjectPlanData, StatusReport

_SECTIONS = (
    "progress",
    "milestones",
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def resolve_as_of(plan: ProjectPlanData) -> str:
    parsed = _parse_date(plan.status_date)
    return (parsed or datetime.now(UTC).date()).isoformat()


def plan_metrics(plan: ProjectPlanData, as_of: str) -> dict:
    as_of_d = date.fromisoformat(as_of)
    horizon = as_of_d + timedelta(days=7)
    due = 0
    done = 0
    overdue = 0
    next_names: list[str] = []
    milestone_notes: list[str] = []
    for task in plan.tasks:
        finish = _parse_date(task.baseline_finish)
        complete = bool(task.actual_finish) or task.percent_complete >= 100
        if finish and finish <= as_of_d:
            due += 1
            if complete:
                done += 1
            else:
                overdue += 1
        if finish and as_of_d < finish <= horizon and not complete:
            next_names.append(task.name)
        if task.is_milestone:
            if complete:
                state = "complete"
            elif finish and finish <= as_of_d:
                state = "due"
            else:
                state = "upcoming"
            milestone_notes.append(f"{task.name}: {state}")
    progress_notes = [
        f"As of {as_of}, {done} of {due} baseline-due tasks are complete.",
        f"Overdue tasks: {overdue}.",
    ]
    if plan.planned_only:
        progress_notes.append("MPP has no actuals; progress is planned-only.")
    return {
        "due_count": due,
        "done_count": done,
        "overdue_count": overdue,
        "next_7_day_names": next_names,
        "milestone_notes": milestone_notes,
        "progress_notes": progress_notes,
    }


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
        snapshot = plan.model_dump()
        snapshot["as_of_date"] = as_of
        snapshot["metrics"] = plan_metrics(plan, as_of)
        report = analyze_wsr(snapshot)
        payload = report.model_dump()
        payload["request_handle"] = handle
        payload["as_of_date"] = as_of
        payload["planned_only"] = plan.planned_only
        for key in _SECTIONS:
            payload.setdefault(key, [])
        StatusReport.model_validate(payload)
        return store.set_status(handle, "succeeded", result=payload)
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

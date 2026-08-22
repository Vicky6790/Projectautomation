from __future__ import annotations

from datetime import UTC, date, datetime

from app import storage as storage_mod
from app.ai.engine import analyze_retrospective
from app.errors import AppError
from app.models import ProcessingResponse, ProjectPlanData, RetrospectiveReport

_SECTIONS = (
    "schedule_variance",
    "milestone_delivery",
    "task_completion",
    "what_went_well",
    "what_went_poorly",
    "lessons_learned",
    "recommendations",
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


def retro_metrics(plan: ProjectPlanData) -> dict:
    today = datetime.now(UTC).date()
    total = 0
    complete = 0
    slipped: list[str] = []
    on_time: list[str] = []
    milestone_notes: list[str] = []
    for task in plan.tasks:
        if task.is_summary:
            continue
        total += 1
        finished = bool(task.actual_finish) or task.percent_complete >= 100
        if finished:
            complete += 1
        baseline = _parse_date(task.baseline_finish)
        actual = _parse_date(task.actual_finish)
        if finished and baseline and actual and actual <= baseline:
            on_time.append(task.name)
        elif finished and baseline and actual and actual > baseline:
            slipped.append(task.name)
        elif not finished and baseline and baseline < today:
            slipped.append(task.name)
        if task.is_milestone:
            if finished:
                state = "delivered"
            elif baseline and baseline < today:
                state = "missed"
            else:
                state = "open"
            milestone_notes.append(f"{task.name}: {state}")
    completion_notes = [f"{complete} of {total} non-summary tasks are complete."]
    schedule_notes = [
        f"{len(on_time)} tasks finished on or before baseline.",
        f"{len(slipped)} tasks slipped the baseline or are overdue.",
    ]
    if plan.planned_only:
        schedule_notes.append("No actuals present; comparison is planned-only.")
    return {
        "schedule_notes": schedule_notes,
        "milestone_notes": milestone_notes,
        "completion_notes": completion_notes,
        "on_time_names": on_time,
        "slipped_names": slipped,
    }


def run_retrospective_generation(handle: str, *, force: bool = False) -> ProcessingResponse:
    store = storage_mod.store
    job = store.create_job("retrospective", handle)
    if job.status == "succeeded" and not force:
        return job
    if job.status == "running":
        return job
    store.set_status(handle, "running")
    try:
        plan = store.get_plan(handle)
        snapshot = plan.model_dump()
        snapshot["planned_only"] = plan.planned_only
        snapshot["metrics"] = retro_metrics(plan)
        report = analyze_retrospective(snapshot)
        payload = report.model_dump()
        payload["request_handle"] = handle
        payload["planned_only"] = plan.planned_only
        payload.pop("plan", None)
        for key in _SECTIONS:
            payload.setdefault(key, [])
        RetrospectiveReport.model_validate(payload)
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
                "code": "RETROSPECTIVE_GENERATION_FAILED",
                "message": "Retrospective generation failed",
                "retryable": True,
            },
        )
        return store.get_job(handle)

"""Central task schedule status. Delay is Finish vs Baseline Finish only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.models import PlanTaskData

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


@dataclass(frozen=True)
class TaskScheduleStatus:
    task_id: str
    task_name: str
    completion_status: str
    delay_status: str
    delay_days: Optional[int]
    overdue_status: str
    baseline_available: bool
    finish_available: bool


def normalize_date(value) -> Optional[date]:
    """Convert MPP/date values to a calendar date. None when unavailable."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:19]).date()
        except ValueError:
            pass
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text[:19] if "T" not in text else text.replace("T", " ")[:19], fmt).date()
            except ValueError:
                continue
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def calculate_task_schedule_status(
    task: PlanTaskData,
    as_of_date,
    *,
    percent_complete: float | None = None,
    baseline_finish=None,
    finish=None,
) -> TaskScheduleStatus:
    """Authoritative delay = current Finish vs Baseline Finish. Dates are never invented."""

    baseline = normalize_date(task.baseline_finish if baseline_finish is None else baseline_finish)
    current_finish = normalize_date(task.scheduled_finish if finish is None else finish)
    as_of = normalize_date(as_of_date)
    progress = task.percent_complete if percent_complete is None else percent_complete

    if progress is None:
        completion_status = "Progress Unavailable"
    elif progress >= 100:
        completion_status = "Completed"
    elif progress > 0:
        completion_status = "In Progress"
    else:
        completion_status = "Not Started"

    delay_days: int | None = None
    if baseline is None:
        delay_status = "Baseline Unavailable"
    elif current_finish is None:
        delay_status = "Insufficient Data"
    else:
        calculated = (current_finish - baseline).days
        delay_days = max(0, calculated)
        delay_status = "Delayed" if calculated > 0 else "No Delay"

    if baseline is None or progress is None:
        overdue_status = "Unavailable"
    elif progress >= 100:
        overdue_status = "Not Overdue"
    elif as_of is None:
        overdue_status = "Unavailable"
    elif as_of > baseline:
        overdue_status = "Overdue"
    else:
        overdue_status = "Not Overdue"

    return TaskScheduleStatus(
        task_id=str(task.id),
        task_name=task.name,
        completion_status=completion_status,
        delay_status=delay_status,
        delay_days=delay_days,
        overdue_status=overdue_status,
        baseline_available=baseline is not None,
        finish_available=current_finish is not None,
    )


def executable_tasks(tasks: list[PlanTaskData]) -> list[PlanTaskData]:
    return [task for task in tasks if not task.is_summary]


def rollup_schedule(
    tasks: list[PlanTaskData],
    as_of_date,
) -> dict[str, int | float | None]:
    leaves = executable_tasks(tasks)
    statuses = [calculate_task_schedule_status(task, as_of_date) for task in leaves]
    total = len(statuses)
    completed = sum(1 for item in statuses if item.completion_status == "Completed")
    in_progress = sum(1 for item in statuses if item.completion_status == "In Progress")
    not_started = sum(1 for item in statuses if item.completion_status == "Not Started")
    delayed = sum(1 for item in statuses if item.delay_status == "Delayed")
    overdue = sum(1 for item in statuses if item.overdue_status == "Overdue")
    delay_percent = None if total == 0 else round(delayed / total * 100, 1)
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "delayed": delayed,
        "overdue": overdue,
        "delay_percent": delay_percent,
    }

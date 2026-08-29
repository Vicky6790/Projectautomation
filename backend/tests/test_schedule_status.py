from datetime import date

from app.models import PlanTaskData
from app.wsr.schedule_status import calculate_task_schedule_status, rollup_schedule


def _task(**kwargs) -> PlanTaskData:
    data = dict(id=145, name="CMS Integration")
    data.update(kwargs)
    return PlanTaskData(**data)


def test_no_delay_when_finish_equals_baseline() -> None:
    status = calculate_task_schedule_status(
        _task(baseline_finish="2026-08-20", scheduled_finish="2026-08-20"),
        "2026-08-30",
    )
    assert status.delay_days == 0
    assert status.delay_status == "No Delay"


def test_delayed_when_finish_after_baseline() -> None:
    status = calculate_task_schedule_status(
        _task(baseline_finish="2026-08-20", scheduled_finish="2026-08-25"),
        "2026-08-30",
    )
    assert status.delay_days == 5
    assert status.delay_status == "Delayed"


def test_finished_early_is_not_delay() -> None:
    status = calculate_task_schedule_status(
        _task(baseline_finish="2026-08-20", scheduled_finish="2026-08-18"),
        "2026-08-30",
    )
    assert status.delay_days == 0
    assert status.delay_status == "No Delay"


def test_missing_baseline_is_unavailable() -> None:
    status = calculate_task_schedule_status(
        _task(scheduled_finish="2026-08-25"),
        "2026-08-30",
    )
    assert status.delay_status == "Baseline Unavailable"
    assert status.delay_days is None


def test_missing_finish_is_insufficient_data() -> None:
    status = calculate_task_schedule_status(
        _task(baseline_finish="2026-08-20"),
        "2026-08-30",
    )
    assert status.delay_status == "Insufficient Data"
    assert status.delay_days is None


def test_incomplete_past_baseline_is_delayed_and_overdue() -> None:
    status = calculate_task_schedule_status(
        _task(
            baseline_finish="2026-08-20",
            scheduled_finish="2026-08-30",
            percent_complete=50,
        ),
        "2026-08-30",
    )
    assert status.delay_status == "Delayed"
    assert status.overdue_status == "Overdue"
    assert status.completion_status == "In Progress"


def test_completed_late_remains_delayed() -> None:
    status = calculate_task_schedule_status(
        _task(
            baseline_finish="2026-08-20",
            scheduled_finish="2026-08-25",
            percent_complete=100,
        ),
        "2026-08-30",
    )
    assert status.delay_status == "Delayed"
    assert status.delay_days == 5
    assert status.completion_status == "Completed"
    assert status.overdue_status == "Not Overdue"


def test_same_calendar_day_ignores_time() -> None:
    status = calculate_task_schedule_status(
        _task(
            baseline_finish="2026-08-30T00:00:00",
            scheduled_finish="2026-08-30T18:00:00",
        ),
        "2026-08-30",
    )
    assert status.delay_days == 0
    assert status.delay_status == "No Delay"


def test_as_of_is_not_used_as_primary_delay() -> None:
    status = calculate_task_schedule_status(
        _task(
            baseline_finish="2026-08-20",
            scheduled_finish="2026-08-20",
            percent_complete=50,
        ),
        "2026-08-30",
    )
    assert status.delay_status == "No Delay"
    assert status.delay_days == 0
    assert status.overdue_status == "Overdue"


def test_phase_rollup_uses_executable_tasks_only() -> None:
    rollup = rollup_schedule(
        [
            PlanTaskData(id=1, name="UX", is_summary=True, baseline_finish="2026-08-20", scheduled_finish="2026-08-30"),
            PlanTaskData(
                id=2,
                name="Wireframes",
                baseline_finish="2026-08-20",
                scheduled_finish="2026-08-25",
                percent_complete=100,
            ),
            PlanTaskData(
                id=3,
                name="Prototype",
                baseline_finish="2026-08-22",
                scheduled_finish="2026-08-22",
                percent_complete=40,
            ),
        ],
        date(2026, 8, 30),
    )
    assert rollup["total"] == 2
    assert rollup["delayed"] == 1
    assert rollup["overdue"] == 1
    assert rollup["delay_percent"] == 50.0

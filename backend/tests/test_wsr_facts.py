from datetime import date

from app.models import PlanPhaseData, PlanTaskData, ProjectPlanData
from app.wsr.facts import derive_wsr_facts


def _plan(
    tasks: list[PlanTaskData],
    *,
    phases: list[PlanPhaseData] | None = None,
) -> ProjectPlanData:
    return ProjectPlanData(
        name="Core Banking",
        owner="Priya Shah",
        tasks=tasks,
        phases=phases or [],
    )


def test_health_off_track_when_go_live_before_as_of() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-08-01",
                )
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.project_health == "off_track"
    assert facts.planned_go_live_date == "2026-08-01"
    assert facts.countdown_days == -21


def test_health_at_risk_when_incomplete_work_is_overdue() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Late build",
                    scheduled_finish="2026-08-10",
                    percent_complete=40,
                ),
                PlanTaskData(
                    id=2,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-01",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.project_health == "at_risk"


def test_health_on_track_when_go_live_future_and_no_overdue() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Kickoff",
                    scheduled_finish="2026-08-01",
                    percent_complete=100,
                    actual_finish="2026-08-01",
                ),
                PlanTaskData(
                    id=2,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-01",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.project_health == "on_track"
    assert facts.as_of_date == "2026-08-22"
    assert facts.generated_at == "2026-08-22T10:00:00Z"


def test_health_unavailable_without_go_live_date() -> None:
    facts = derive_wsr_facts(
        _plan([PlanTaskData(id=1, name="Unscheduled work")]),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.project_health == "unavailable"
    assert facts.planned_go_live_date is None
    assert facts.countdown_days is None


def test_does_not_substitute_baseline_for_go_live() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Go Live",
                    is_milestone=True,
                    baseline_finish="2026-09-01",
                )
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.planned_go_live_date is None
    assert facts.project_health == "unavailable"


def test_timeline_unavailable_without_phase_dates() -> None:
    facts = derive_wsr_facts(
        _plan(
            [PlanTaskData(id=1, name="Work")],
            phases=[PlanPhaseData(id=10, name="Build")],
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.timeline is None
    assert facts.phase_statuses[0].state == "not_started"


def test_go_live_prefers_gate_field() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Release",
                    gate="Go-Live",
                    scheduled_finish="2026-10-15",
                ),
                PlanTaskData(
                    id=2,
                    name="Other milestone",
                    is_milestone=True,
                    scheduled_finish="2026-09-01",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.planned_go_live_date == "2026-10-15"
    assert date.fromisoformat(facts.planned_go_live_date) == date(2026, 10, 15)

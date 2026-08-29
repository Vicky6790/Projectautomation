from datetime import date

from app.models import PlanAssignmentData, PlanTaskData, ProjectPlanData
from app.wsr.delay_engine import _RECONCILE_WARNING, match_task
from app.wsr.facts import derive_wsr_facts


def _plan(tasks: list[PlanTaskData], **kwargs) -> ProjectPlanData:
    return ProjectPlanData(name="Core Banking", owner="Priya Shah", tasks=tasks, **kwargs)


def _go_live(**kwargs) -> PlanTaskData:
    data = dict(
        id=90,
        name="Go Live",
        is_milestone=True,
        baseline_finish="2026-08-20",
        scheduled_finish="2026-09-01",
    )
    data.update(kwargs)
    return PlanTaskData(**data)


def test_no_go_live_shift() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                ),
                _go_live(baseline_finish="2026-09-01", scheduled_finish="2026-09-01"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.actual_shift_working_days == 0
    assert mapping.shift_working_days == 0
    assert mapping.rows == []
    assert mapping.total_delayed_days == 0
    assert mapping.reconciliation_status == "reconciled"


def test_go_live_shifted_by_working_days() -> None:
    mapping = derive_wsr_facts(
        _plan([_go_live()]),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.baseline_go_live == "2026-08-20"
    assert mapping.current_go_live == "2026-09-01"
    assert mapping.shift_working_days == 8
    assert mapping.actual_shift_working_days == 8


def test_weekend_inside_shift_period_is_not_counted() -> None:
    mapping = derive_wsr_facts(
        _plan([_go_live()]),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.shift_working_days == 8
    assert date(2026, 8, 22).weekday() == 5


def test_holiday_inside_shift_period() -> None:
    mapping = derive_wsr_facts(
        ProjectPlanData(
            name="Core Banking",
            calendar_available=True,
            holiday_dates=["2026-08-26"],
            tasks=[_go_live()],
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.shift_working_days == 8
    assert mapping.holidays == 1
    assert mapping.actual_shift_working_days == 7
    assert mapping.calendar_source == "project"


def test_completed_delayed_task_is_still_delay() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                    percent_complete=100,
                    actual_finish="2026-08-13",
                    assignments=[PlanAssignmentData(resource_name="Idealake")],
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Design Sign-off"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 3
    assert mapping.rows[0].owner == "Idealake"


def test_delayed_existing_task_not_classified_by_name() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="UX Phase",
                    wbs="1.1",
                    is_summary=True,
                ),
                PlanTaskData(
                    id=2,
                    name="Design Sign-off",
                    wbs="1.1.1",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-20",
                ),
                _go_live(id=3, wbs="1.2"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Design Sign-off"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 8
    assert mapping.rows[0].parent_name == "UX Phase"


def test_new_additional_task_without_baseline() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Unplanned review round",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=[PlanAssignmentData(resource_name="PNB MetLife")],
                ),
                _go_live(scheduled_finish="2026-08-27"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Unplanned review round"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 5
    assert mapping.rows[0].owner == "PNB MetLife"
    assert mapping.actual_shift_working_days == 5
    assert mapping.total_delayed_days == 5
    assert mapping.reconciliation_status == "reconciled"


def test_name_containing_additional_is_not_enough_to_classify() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Additional Days Due To Unplanned Round 2 Feedback",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                ),
                _go_live(baseline_finish="2026-09-01", scheduled_finish="2026-09-01"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows == []
    assert mapping.actual_shift_working_days == 0


def test_additional_task_running_in_parallel_is_not_counted() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Critical path work",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-20",
                ),
                PlanTaskData(
                    id=2,
                    name="Side analysis",
                    scheduled_start="2026-08-03",
                    scheduled_finish="2026-08-14",
                ),
                _go_live(id=3, predecessor_ids=[1]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    names = [row.name for row in mapping.rows]
    assert "Side analysis" not in names
    assert names == ["Critical path work"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 8


def test_additional_task_extending_go_live() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Extra UAT cycle",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    predecessor_ids=[],
                ),
                _go_live(id=2, scheduled_finish="2026-08-27", predecessor_ids=[1]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Extra UAT cycle"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 5
    assert mapping.actual_shift_working_days == 5
    assert mapping.reconciliation_status == "reconciled"


def test_sequential_delayed_tasks_are_not_double_counted() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                ),
                PlanTaskData(
                    id=2,
                    name="HTML delivery",
                    baseline_finish="2026-08-13",
                    scheduled_finish="2026-08-20",
                    predecessor_ids=[1],
                ),
                _go_live(id=3, predecessor_ids=[2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    by_name = {row.name: row.shift_days for row in mapping.rows}
    assert by_name["Sign-off"] == 3
    assert by_name["HTML delivery"] == 5
    assert sum(by_name.values()) == 8
    assert mapping.total_delayed_days == 8
    assert mapping.actual_shift_working_days == 8
    assert mapping.reconciliation_status == "reconciled"


def test_parallel_delayed_tasks_are_not_double_counted() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-20",
                ),
                PlanTaskData(
                    id=2,
                    name="Review cycle",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-20",
                ),
                _go_live(id=3, predecessor_ids=[1, 2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.actual_shift_working_days == 8
    assert mapping.total_delayed_days == 8
    assert sum(row.shift_days or 0 for row in mapping.rows) == 8
    assert len(mapping.rows) == 1
    assert mapping.reconciliation_status == "reconciled"


def test_duplicate_task_names_match_by_id_not_name() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Review",
                    wbs="1.1.1",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                ),
                PlanTaskData(
                    id=2,
                    name="Review",
                    wbs="1.2.1",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                ),
                _go_live(id=3),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Review"]
    assert mapping.rows[0].current_task_id == 1
    assert mapping.rows[0].shift_days == 3


def test_ambiguous_mapping_requires_validation() -> None:
    from app.wsr.delay_engine import _baseline_index, build_delay_mapping
    from app.wsr.facts import parse_date

    current = PlanTaskData(id=99, name="Review", wbs="", outline_level=3)
    baseline_tasks = [
        PlanTaskData(
            id=1,
            name="Review",
            wbs="1.1.1",
            outline_level=3,
            baseline_finish="2026-08-01",
        ),
        PlanTaskData(
            id=2,
            name="Review",
            wbs="1.2.1",
            outline_level=3,
            baseline_finish="2026-08-01",
        ),
    ]
    index = _baseline_index(baseline_tasks, from_embedded_baseline=True, parse_date=parse_date)
    matched, source = match_task(current, index)
    assert matched is None
    assert source == "ambiguous"

    mapping = build_delay_mapping(
        _plan(
            [
                PlanTaskData(
                    id=99,
                    name="Review",
                    outline_level=3,
                    scheduled_start="2026-08-11",
                    scheduled_finish="2026-08-13",
                ),
                _go_live(id=3, scheduled_finish="2026-09-01"),
            ]
        ),
        date(2026, 8, 22),
        [],
        date(2026, 9, 1),
        baseline_plan=_plan(
            [
                PlanTaskData(
                    id=1,
                    name="Review",
                    wbs="1.1.1",
                    outline_level=3,
                    baseline_finish="2026-08-01",
                    scheduled_finish="2026-08-01",
                ),
                PlanTaskData(
                    id=2,
                    name="Review",
                    wbs="1.2.1",
                    outline_level=3,
                    baseline_finish="2026-08-01",
                    scheduled_finish="2026-08-01",
                ),
                _go_live(id=3, scheduled_finish="2026-08-20"),
            ]
        ),
    )
    assert mapping.matching_requires_validation is True
    assert mapping.rows == []
    assert mapping.reconciliation_status == "requires_validation"
    assert mapping.reconciliation_warning == _RECONCILE_WARNING


def test_multiple_phases_group_rows() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="UX Phase", wbs="1.1", is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Wireframes",
                    wbs="1.1.1",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                ),
                PlanTaskData(id=3, name="HTML Phase", wbs="1.2", is_summary=True),
                PlanTaskData(
                    id=4,
                    name="Templates",
                    wbs="1.2.1",
                    baseline_finish="2026-08-13",
                    scheduled_finish="2026-08-20",
                ),
                _go_live(id=5, wbs="1.3"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.parent_name for row in mapping.rows] == ["UX Phase", "HTML Phase"]


def test_multiple_delayed_tasks_in_one_phase() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Design Phase", wbs="1.1", is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Desktop designs",
                    wbs="1.1.1",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                ),
                PlanTaskData(
                    id=3,
                    name="Mobile designs",
                    wbs="1.1.2",
                    baseline_finish="2026-08-13",
                    scheduled_finish="2026-08-20",
                ),
                _go_live(id=4, wbs="1.2"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.parent_name for row in mapping.rows] == ["Design Phase", "Design Phase"]
    assert mapping.total_delayed_days == 8


def test_multiple_additional_tasks() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Round 2 feedback",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-24",
                ),
                PlanTaskData(
                    id=2,
                    name="Round 3 feedback",
                    scheduled_start="2026-08-25",
                    scheduled_finish="2026-08-27",
                ),
                _go_live(id=3, scheduled_finish="2026-08-27", predecessor_ids=[1, 2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.task_type for row in mapping.rows] == ["additional", "additional"]
    assert mapping.total_delayed_days == 5
    assert mapping.actual_shift_working_days == 5
    assert mapping.reconciliation_status == "reconciled"


def test_zero_day_milestone_is_excluded() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Gate checkpoint",
                    is_milestone=True,
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == []


def test_go_live_milestone_is_excluded_from_rows() -> None:
    mapping = derive_wsr_facts(
        _plan([_go_live()]),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows == []
    assert mapping.actual_shift_working_days == 8
    assert mapping.total_delayed_days == 0
    assert mapping.reconciliation_status == "requires_validation"
    assert mapping.reconciliation_warning == _RECONCILE_WARNING


def test_total_count_reconciles_when_equal() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-20",
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 8
    assert mapping.reconciliation_status == "reconciled"
    assert mapping.reconciliation_warning is None


def test_total_count_mismatch_is_not_forced() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows[0].shift_days == 3
    assert mapping.total_delayed_days == 3
    assert mapping.actual_shift_working_days == 8
    assert mapping.reconciliation_status == "requires_validation"
    assert mapping.reconciliation_warning == _RECONCILE_WARNING


def test_missing_baseline_go_live() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
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
    ).delay_mapping
    assert mapping.baseline_go_live is None
    assert mapping.actual_shift_working_days is None
    assert mapping.reconciliation_status == "unavailable"


def test_missing_current_go_live() -> None:
    mapping = derive_wsr_facts(
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
    ).delay_mapping
    assert mapping.current_go_live is None
    assert mapping.actual_shift_working_days is None
    assert mapping.reconciliation_status == "unavailable"

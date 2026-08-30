from datetime import date

from app.models import PlanAssignmentData, PlanTaskData, ProjectPlanData
from app.wsr.delay_engine import _RECONCILE_WARNING, match_task
from app.wsr.facts import derive_wsr_facts


def _owners(*names: str) -> list[PlanAssignmentData]:
    return [PlanAssignmentData(resource_name=name) for name in names]


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
                    name="Delay In Presenting Mobile Wireframes",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-13",
                    assignments=_owners("Idealake"),
                ),
                _go_live(baseline_finish="2026-09-01", scheduled_finish="2026-09-01"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.actual_shift_working_days == 0
    assert mapping.rows == []
    assert mapping.total_delayed_days == 0
    assert mapping.unattributed_shift_days == 0


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


def test_named_delay_with_owner_is_listed() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                    assignments=_owners("Idealake"),
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Delay In Presenting Mobile Wireframes"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 3
    assert mapping.rows[0].owner == "Idealake"
    assert mapping.unattributed_shift_days == 0


def test_finish_after_baseline_is_delay() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Design Sign-off",
                    baseline_finish="2026-08-20",
                    scheduled_finish="2026-09-01",
                    assignments=_owners("Idealake"),
                ),
                _go_live(id=2, predecessor_ids=[1]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Design Sign-off"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].planned_finish == "2026-08-20"
    assert mapping.rows[0].revised_finish == "2026-09-01"
    assert mapping.rows[0].shift_days == 8
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 8
    assert mapping.unattributed_shift_days == 0


def test_ownerless_named_delay_is_listed() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Delay In Presenting Mobile Wireframes"]
    assert mapping.rows[0].owner is None


def test_work_before_go_live_window_is_not_listed() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-03",
                    scheduled_finish="2026-08-05",
                    assignments=_owners("Idealake"),
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows == []
    assert mapping.actual_shift_working_days == 8


def test_named_additional_with_shared_owner() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Additional Days Due To Unplanned Round 2 Feedback",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-24",
                    assignments=_owners("Idealake", "PNB MetLife"),
                ),
                _go_live(scheduled_finish="2026-08-27"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == [
        "Additional Days Due To Unplanned Round 2 Feedback"
    ]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 2
    assert mapping.rows[0].owner == "Idealake & PNB MetLife"


def test_unmatched_new_work_with_owner_is_additional() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Competitive Analysis Step",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake", "PNB MetLife"),
                ),
                _go_live(scheduled_finish="2026-08-27"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Competitive Analysis Step"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 5
    assert mapping.actual_shift_working_days == 5
    assert mapping.total_delayed_days == 5
    assert mapping.unattributed_shift_days == 0


def test_additional_without_go_live_link_breaks_down_five_day_shift() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Unplanned review round",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake"),
                ),
                PlanTaskData(
                    id=2,
                    name="Build",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                ),
                _go_live(id=3, scheduled_finish="2026-08-27", predecessor_ids=[2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["Unplanned review round"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].planned_finish is None
    assert mapping.rows[0].shift_days == 5
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 5


def test_additional_task_running_in_parallel_is_not_counted() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Completion Of Designs",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-09-01",
                    assignments=_owners("Idealake"),
                ),
                PlanTaskData(
                    id=2,
                    name="Side analysis",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake"),
                ),
                _go_live(id=3, predecessor_ids=[1]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == [
        "Delay In Completion Of Designs",
        "Side analysis",
    ]
    assert [row.task_type for row in mapping.rows] == ["additional", "additional"]
    assert [row.shift_days for row in mapping.rows] == [3, 5]
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 8


def test_additional_task_extending_go_live() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Additional Days Due To Unplanned Round 2 Feedback",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake", "PNB MetLife"),
                ),
                _go_live(id=2, scheduled_finish="2026-08-27", predecessor_ids=[1]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 5
    assert mapping.total_delayed_days == 5
    assert mapping.unattributed_shift_days == 0


def test_sequential_named_delays_are_not_double_counted() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                    assignments=_owners("Idealake"),
                ),
                PlanTaskData(
                    id=2,
                    name="Delay In Sharing Sign-Off",
                    scheduled_start="2026-08-26",
                    scheduled_finish="2026-09-01",
                    predecessor_ids=[1],
                    assignments=_owners("PNB MetLife"),
                ),
                _go_live(id=3, predecessor_ids=[2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    by_name = {row.name: row.shift_days for row in mapping.rows}
    assert by_name["Delay In Presenting Mobile Wireframes"] == 3
    assert by_name["Delay In Sharing Sign-Off"] == 5
    assert mapping.total_delayed_days == 8
    assert mapping.actual_shift_working_days == 8
    assert mapping.unattributed_shift_days == 0


def test_leftover_shift_is_not_shown_as_unattributed() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                    assignments=_owners("Idealake"),
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
    assert mapping.unattributed_shift_days == 0
    assert mapping.reconciliation_warning is None


def test_duplicate_task_names_match_by_id_not_name() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Sharing Sign-Off",
                    wbs="1.1.1",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                    assignments=_owners("PNB MetLife"),
                ),
                PlanTaskData(
                    id=2,
                    name="Delay In Sharing Sign-Off",
                    wbs="1.2.1",
                    assignments=_owners("PNB MetLife"),
                ),
                _go_live(id=3),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.current_task_id for row in mapping.rows] == [1]
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
                    assignments=_owners("Idealake"),
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
    assert mapping.reconciliation_warning == _RECONCILE_WARNING


def test_multiple_phases_group_rows() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="UX Phase", wbs="1.1", is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Delay In Presenting Mobile Wireframes",
                    wbs="1.1.1",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-25",
                    assignments=_owners("Idealake"),
                ),
                PlanTaskData(id=3, name="HTML Phase", wbs="1.2", is_summary=True),
                PlanTaskData(
                    id=4,
                    name="Delay In Completion Of HTMLs",
                    wbs="1.2.1",
                    scheduled_start="2026-08-26",
                    scheduled_finish="2026-09-01",
                    assignments=_owners("Idealake"),
                ),
                _go_live(id=5, wbs="1.3"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.parent_name for row in mapping.rows] == ["UX Phase", "HTML Phase"]


def test_multiple_named_delays_in_one_phase() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Design Phase", wbs="1.1", is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Delay In Completion Of Designs",
                    wbs="1.1.1",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-21",
                    assignments=_owners("Idealake"),
                ),
                PlanTaskData(
                    id=3,
                    name="Delay In Sharing Sign-Off",
                    wbs="1.1.2",
                    scheduled_start="2026-08-24",
                    scheduled_finish="2026-09-01",
                    assignments=_owners("PNB MetLife"),
                ),
                _go_live(id=4, wbs="1.2"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.parent_name for row in mapping.rows] == ["Design Phase", "Design Phase"]
    assert mapping.total_delayed_days == 8
    assert mapping.unattributed_shift_days == 0


def test_multiple_additional_tasks() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Additional Days Due To Unplanned Round 2 Feedback",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-24",
                    assignments=_owners("Idealake", "PNB MetLife"),
                ),
                PlanTaskData(
                    id=2,
                    name="Additional Days Due To Unplanned Round 3 Feedback",
                    scheduled_start="2026-08-25",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake", "PNB MetLife"),
                ),
                _go_live(id=3, scheduled_finish="2026-08-27", predecessor_ids=[1, 2]),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.task_type for row in mapping.rows] == ["additional", "additional"]
    assert mapping.total_delayed_days == 5
    assert mapping.unattributed_shift_days == 0


def test_go_live_milestone_is_excluded_from_rows() -> None:
    mapping = derive_wsr_facts(
        _plan([_go_live()]),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows == []
    assert mapping.actual_shift_working_days == 8
    assert mapping.total_delayed_days == 0
    assert mapping.unattributed_shift_days == 0
    assert mapping.reconciliation_warning is None


def test_named_tasks_can_fill_actual_shift() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-09-01",
                    assignments=_owners("Idealake"),
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 8
    assert mapping.unattributed_shift_days == 0
    assert mapping.reconciliation_warning is None


def test_missing_baseline_go_live() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Delay In Presenting Mobile Wireframes",
                    scheduled_finish="2026-08-13",
                    assignments=_owners("Idealake"),
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
    assert mapping.rows == []


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
    assert mapping.rows == []


def test_additional_not_listed_when_go_live_did_not_shift() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Competitive Analysis Step",
                    scheduled_start="2026-08-21",
                    scheduled_finish="2026-08-27",
                    assignments=_owners("Idealake"),
                ),
                _go_live(baseline_finish="2026-09-01", scheduled_finish="2026-09-01"),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.actual_shift_working_days == 0
    assert mapping.rows == []
    assert mapping.total_delayed_days == 0


def test_on_time_task_is_not_listed() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Kickoff",
                    baseline_finish="2026-08-10",
                    scheduled_finish="2026-08-10",
                    actual_finish="2026-08-10",
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert mapping.rows == []


def test_actual_finish_is_used_when_present() -> None:
    mapping = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="CMS Integration",
                    baseline_finish="2026-08-20",
                    scheduled_finish="2026-08-20",
                    actual_finish="2026-09-01",
                    assignments=_owners("Idealake"),
                ),
                _go_live(),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping
    assert [row.name for row in mapping.rows] == ["CMS Integration"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].revised_finish == "2026-09-01"
    assert mapping.rows[0].shift_days == 8
    assert mapping.total_delayed_days == mapping.actual_shift_working_days == 8

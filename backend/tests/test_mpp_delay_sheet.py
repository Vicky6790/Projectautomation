from app.models import PlanAssignmentData, PlanTaskData, ProjectPlanData
from app.wsr.mpp_delay_sheet import build_delay_sheet, classify_marked_type, delay_days


def _plan(tasks: list[PlanTaskData], **kwargs) -> ProjectPlanData:
    return ProjectPlanData(name="Demo", owner="Alex PM", tasks=tasks, **kwargs)


def _task(
    task_id: int,
    name: str,
    *,
    wbs: str | None = None,
    is_summary: bool = False,
    is_milestone: bool = False,
    baseline0_finish: str | None = None,
    baseline_finish: str | None = None,
    scheduled_finish: str | None = None,
    actual_finish: str | None = None,
    critical: bool | None = None,
    delay_or_additional: str | None = None,
    duration_days: float | None = None,
    baseline0_duration_days: float | None = None,
    predecessor_ids: list[int] | None = None,
    predecessor_names: list[str] | None = None,
    owner: str | None = None,
) -> PlanTaskData:
    assignments = [PlanAssignmentData(resource_name=owner)] if owner else []
    return PlanTaskData(
        id=task_id,
        name=name,
        wbs=wbs,
        is_summary=is_summary,
        is_milestone=is_milestone,
        baseline0_finish=baseline0_finish,
        baseline_finish=baseline_finish,
        scheduled_finish=scheduled_finish,
        actual_finish=actual_finish,
        critical=critical,
        delay_or_additional=delay_or_additional,
        duration_days=duration_days,
        baseline0_duration_days=baseline0_duration_days,
        predecessor_ids=predecessor_ids or [],
        predecessor_names=predecessor_names or [],
        assignments=assignments,
    )


def test_delay_days_actual_after_planned() -> None:
    assert delay_days("2026-08-10", "2026-08-13") == 3


def test_classify_delay_and_additional_marks() -> None:
    assert classify_marked_type("Delay") == "delay"
    assert classify_marked_type("Additional") == "additional"
    assert classify_marked_type("Delay And Or Additional") is None
    assert classify_marked_type("") is None
    assert classify_marked_type(None) is None


def test_sheet_lists_only_tagged_tasks_that_shift_go_live() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(1, "Wireframe Phase", wbs="1", is_summary=True),
                _task(
                    2,
                    "Competitive Analysis Step",
                    wbs="1.1",
                    baseline0_finish="2026-08-10",
                    scheduled_finish="2026-08-17",
                    delay_or_additional="Additional",
                    owner="Idealake & PNB MetLife",
                ),
                _task(
                    3,
                    "Delay In Presenting Mobile Wireframes",
                    wbs="1.2",
                    baseline0_finish="2026-08-18",
                    scheduled_finish="2026-08-21",
                    delay_or_additional="Delay",
                    predecessor_ids=[2],
                    predecessor_names=["Competitive Analysis Step"],
                    owner="Idealake",
                ),
                _task(
                    4,
                    "Offline Review",
                    wbs="1.3",
                    baseline0_finish="2026-08-01",
                    scheduled_finish="2026-08-08",
                    delay_or_additional="Delay",
                    critical=True,
                ),
                _task(
                    5,
                    "Build",
                    wbs="1.4",
                    baseline0_finish="2026-08-20",
                    scheduled_finish="2026-08-25",
                    actual_finish="2026-08-25",
                    critical=True,
                ),
                _task(
                    6,
                    "Go Live",
                    wbs="1.5",
                    is_milestone=True,
                    baseline0_finish="2026-08-20",
                    scheduled_finish="2026-09-01",
                    predecessor_ids=[3],
                    predecessor_names=["Delay In Presenting Mobile Wireframes"],
                ),
            ]
        )
    )
    assert [row.name for row in mapping.rows] == [
        "Competitive Analysis Step",
        "Delay In Presenting Mobile Wireframes",
    ]
    first, second = mapping.rows
    assert first.task_type == "additional"
    assert first.shift_days == 5
    assert first.owner == "Idealake & PNB MetLife"
    assert first.parent_name == "Wireframe Phase"
    assert second.task_type == "delay"
    assert second.shift_days == 3
    assert second.planned_finish == "2026-08-18"
    assert second.revised_finish == "2026-08-21"
    assert mapping.baseline_go_live == "2026-08-20"
    assert mapping.current_go_live == "2026-09-01"
    assert mapping.delayed_task_count == 1
    assert mapping.additional_task_count == 1
    assert mapping.total_delayed_days == 8


def test_duration_growth_on_go_live_path_is_listed() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "API Work",
                    wbs="1.1",
                    delay_or_additional="Additional",
                    duration_days=8,
                    baseline0_duration_days=3,
                    owner="Idealake",
                ),
                _task(
                    2,
                    "Go Live",
                    wbs="1.2",
                    is_milestone=True,
                    baseline0_finish="2026-08-20",
                    scheduled_finish="2026-09-01",
                    predecessor_ids=[1],
                ),
            ]
        )
    )
    assert [row.name for row in mapping.rows] == ["API Work"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days == 5


def test_skips_blank_task_names() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "   ",
                    baseline0_finish="2026-08-17",
                    scheduled_finish="2026-08-20",
                    delay_or_additional="Delay",
                    critical=True,
                ),
                _task(
                    2,
                    "Design",
                    baseline0_finish="2026-08-17",
                    scheduled_finish="2026-08-20",
                    delay_or_additional="Delay",
                    critical=True,
                ),
            ]
        )
    )
    assert [row.name for row in mapping.rows] == ["Design"]
    assert mapping.rows[0].shift_days == 3


def test_planned_finish_uses_baseline_0_not_get_baseline_finish() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "Build",
                    baseline_finish="2026-08-01",
                    baseline0_finish="2026-08-20",
                    scheduled_finish="2026-08-27",
                    delay_or_additional="Delay",
                    critical=True,
                )
            ]
        )
    )
    row = mapping.rows[0]
    assert row.planned_finish == "2026-08-20"
    assert row.shift_days == 5


def test_untagged_critical_delay_is_not_listed() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "Build",
                    baseline0_finish="2026-08-20",
                    scheduled_finish="2026-08-25",
                    actual_finish="2026-08-25",
                    critical=True,
                )
            ]
        )
    )
    assert mapping.rows == []


def test_inserted_delay_without_baseline_uses_duration() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "UX Approval Delay Due Team's unavailability",
                    delay_or_additional="Delay",
                    duration_days=5,
                    scheduled_finish="2026-09-02",
                    critical=True,
                    owner="PNB MetLife",
                ),
                _task(
                    2,
                    "Go Live",
                    is_milestone=True,
                    baseline_finish="2027-03-26",
                    scheduled_finish="2027-04-02",
                    predecessor_ids=[1],
                ),
            ]
        )
    )
    assert [row.name for row in mapping.rows] == ["UX Approval Delay Due Team's unavailability"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 5
    assert mapping.rows[0].planned_finish is None
    assert mapping.actual_shift_working_days == 5


def test_tagged_task_with_unchanged_finish_is_not_listed() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    1,
                    "Delay In Receiving Feedback On IA",
                    delay_or_additional="Delay",
                    baseline_finish="2026-08-11",
                    scheduled_finish="2026-08-11",
                    duration_days=34,
                    critical=True,
                ),
                _task(
                    2,
                    "Go Live",
                    is_milestone=True,
                    baseline_finish="2027-03-26",
                    scheduled_finish="2027-04-02",
                    predecessor_ids=[1],
                ),
            ]
        )
    )
    assert mapping.rows == []


def test_parallel_inserted_delays_keep_only_go_live_driver() -> None:
    mapping = build_delay_sheet(
        _plan(
            [
                _task(
                    10,
                    "UX Approach",
                    wbs="1",
                    is_summary=True,
                    critical=True,
                    baseline_finish="2026-08-26",
                    scheduled_finish="2026-09-02",
                ),
                _task(
                    1,
                    "UX Approval Delay Due Team's unavailability",
                    wbs="1.1",
                    delay_or_additional="Delay",
                    duration_days=5,
                    scheduled_finish="2026-09-02",
                    critical=True,
                    predecessor_ids=[643],
                    predecessor_names=["UX Approach Approval"],
                ),
                _task(
                    20,
                    "Set 1 (Template 1)",
                    wbs="2",
                    is_summary=True,
                    critical=False,
                    baseline_finish="2026-08-31",
                    scheduled_finish="2026-09-07",
                ),
                _task(
                    2,
                    "Delay in Sharing Walkthrough of Wireframe due Team's unavailbility",
                    wbs="2.1",
                    delay_or_additional="Delay",
                    duration_days=5,
                    scheduled_finish="2026-09-01",
                    critical=False,
                    predecessor_ids=[35],
                    predecessor_names=["Wireframe Walkthrough And Sharing Wireframe With IBL Team"],
                ),
                _task(
                    3,
                    "Go Live",
                    wbs="3",
                    is_milestone=True,
                    baseline_finish="2027-03-26",
                    scheduled_finish="2027-04-02",
                    predecessor_ids=[10],
                    predecessor_names=["UX Approach"],
                ),
            ]
        )
    )
    assert [row.name for row in mapping.rows] == ["UX Approval Delay Due Team's unavailability"]
    assert mapping.rows[0].shift_days == 5
    assert mapping.actual_shift_working_days == 5
    assert mapping.total_delayed_days == 5


def test_delay_column_alias_matches_tasks_suffix() -> None:
    from app.mpp.reader import _DELAY_OR_ADDITIONAL_ALIASES, _field_label_matches

    assert _field_label_matches(
        "Delay And Or Additional Tasks", _DELAY_OR_ADDITIONAL_ALIASES, contains=True
    )
    assert _field_label_matches(
        "Delay And Or Additional", _DELAY_OR_ADDITIONAL_ALIASES, contains=True
    )
    assert not _field_label_matches("Gate", _DELAY_OR_ADDITIONAL_ALIASES, contains=True)
    assert not _field_label_matches("indendation", _DELAY_OR_ADDITIONAL_ALIASES, contains=True)

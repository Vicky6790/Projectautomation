import logging

from app.models import PlanTaskData, ProjectPlanData
from app.wsr.new_tasks import build_new_task_mapping


def _task(
    task_id: int,
    name: str,
    *,
    wbs: str | None = None,
    guid: str | None = None,
    is_summary: bool = False,
    is_milestone: bool = False,
    percent_complete: float = 0,
    scheduled_start: str | None = "2026-09-01",
    scheduled_finish: str | None = "2026-09-05",
    baseline_finish: str | None = None,
    predecessor_names: list[str] | None = None,
    predecessor_ids: list[int] | None = None,
    outline_level: int = 1,
) -> PlanTaskData:
    return PlanTaskData(
        id=task_id,
        guid=guid,
        name=name,
        wbs=wbs,
        outline_level=outline_level,
        is_summary=is_summary,
        is_milestone=is_milestone,
        percent_complete=percent_complete,
        scheduled_start=scheduled_start,
        scheduled_finish=scheduled_finish,
        baseline_finish=baseline_finish,
        predecessor_names=predecessor_names or [],
        predecessor_ids=predecessor_ids or [],
    )


def _plan(tasks: list[PlanTaskData]) -> ProjectPlanData:
    return ProjectPlanData(name="Demo", owner="Alex PM", tasks=tasks)


def test_example_inserts_two_new_tasks_only() -> None:
    baseline = _plan(
        [
            _task(1, "Project Planning", wbs="1"),
            _task(2, "IA Creation", wbs="2"),
            _task(3, "UX Design", wbs="3"),
            _task(4, "UI Design", wbs="4"),
            _task(5, "UAT", wbs="5"),
        ]
    )
    current = _plan(
        [
            _task(1, "Project Planning", wbs="1"),
            _task(2, "IA Creation", wbs="2"),
            _task(3, "UX Design", wbs="3"),
            _task(4, "UI Design", wbs="4"),
            _task(6, "Client Review Meeting", wbs="5", predecessor_names=["UI Design"]),
            _task(7, "Additional Approval", wbs="6"),
            _task(5, "UAT", wbs="7"),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Client Review Meeting", "Additional Approval"]
    assert {row.task_type for row in mapping.rows} == {"new_task"}
    assert {row.source for row in mapping.rows} == {"Current MPP"}
    assert mapping.new_task_count == 2
    assert mapping.matched_task_count == 5
    assert mapping.new_task_count == len(mapping.rows)


def test_inserted_task_does_not_mark_shifted_existing_tasks_as_new() -> None:
    """Unique IDs stay stable when MS Project row IDs and WBS numbers shift."""
    baseline = _plan(
        [
            _task(10, "Project Planning", wbs="1"),
            _task(20, "IA Creation", wbs="2"),
            _task(30, "UX Design", wbs="3"),
            _task(40, "UI Design", wbs="4"),
            _task(50, "UAT", wbs="5"),
        ]
    )
    current = _plan(
        [
            _task(10, "Project Planning", wbs="1"),
            _task(20, "IA Creation", wbs="2"),
            _task(30, "UX Design", wbs="3"),
            _task(40, "UI Design", wbs="4"),
            _task(60, "Client Review Meeting", wbs="5"),
            _task(50, "UAT", wbs="6"),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Client Review Meeting"]
    assert [row.current_task_id for row in mapping.rows] == [60]
    assert mapping.matched_task_count == 5
    existing = {"Project Planning", "IA Creation", "UX Design", "UI Design", "UAT"}
    assert existing.isdisjoint({row.name for row in mapping.rows})


def test_regenerated_unique_ids_match_wbs_and_name() -> None:
    baseline = _plan(
        [
            _task(1, "Project Planning", wbs="1"),
            _task(2, "IA Creation", wbs="2"),
            _task(3, "UAT", wbs="3"),
        ]
    )
    current = _plan(
        [
            _task(101, "Project Planning", wbs="1"),
            _task(102, "IA Creation", wbs="2"),
            _task(103, "Client Review Meeting", wbs="3"),
            _task(104, "UAT", wbs="4"),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Client Review Meeting"]
    assert mapping.rows[0].calculation_source in {"wbs_name", "hierarchy"}
    assert mapping.matched_task_count == 3


def test_shifted_wbs_still_matches_by_name_and_parent() -> None:
    baseline = _plan(
        [
            _task(1, "Delivery", wbs="1", is_summary=True),
            _task(2, "UX Design", wbs="1.1", outline_level=2),
            _task(3, "UI Design", wbs="1.2", outline_level=2),
            _task(4, "UAT", wbs="1.3", outline_level=2),
        ]
    )
    current = _plan(
        [
            _task(11, "Delivery", wbs="1", is_summary=True),
            _task(12, "UX Design", wbs="1.1", outline_level=2),
            _task(13, "UI Design", wbs="1.2", outline_level=2),
            _task(14, "Client Review Meeting", wbs="1.3", outline_level=2),
            _task(15, "UAT", wbs="1.4", outline_level=2),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Client Review Meeting"]
    assert mapping.matched_task_count == 4
    assert mapping.rows[0].parent_name == "Delivery"


def test_includes_summary_milestone_and_completed_new_tasks() -> None:
    baseline = _plan([_task(1, "Kickoff", wbs="1")])
    current = _plan(
        [
            _task(1, "Kickoff", wbs="1"),
            _task(2, "New Phase", wbs="2", is_summary=True),
            _task(3, "New Gate", wbs="3", is_milestone=True),
            _task(4, "Finished Extra", wbs="4", percent_complete=100),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert {row.name for row in mapping.rows} == {"New Phase", "New Gate", "Finished Extra"}
    assert mapping.new_task_count == 3


def test_guid_match_beats_changed_wbs() -> None:
    baseline = _plan(
        [
            _task(1, "UX Design", wbs="1", guid="aaa-1"),
            _task(2, "UAT", wbs="2", guid="bbb-2"),
        ]
    )
    current = _plan(
        [
            _task(1, "UX Design", wbs="3", guid="aaa-1"),
            _task(9, "Client Review", wbs="2", guid="ccc-9"),
            _task(2, "UAT", wbs="4", guid="bbb-2"),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Client Review"]
    assert mapping.matched_task_count == 2


def test_ambiguous_wbs_name_is_not_classified_as_new() -> None:
    baseline = _plan(
        [
            _task(1, "Review", wbs="1.1"),
            _task(2, "Review", wbs="1.1"),
        ]
    )
    current = _plan(
        [
            _task(10, "Review", wbs="1.1"),
            _task(11, "Brand new", wbs="2"),
        ]
    )
    mapping = build_new_task_mapping(current, baseline)
    assert [row.name for row in mapping.rows] == ["Brand new"]
    assert mapping.ambiguous_task_count == 1
    assert mapping.review_rows[0].match_status == "ambiguous"
    assert mapping.review_rows[0].task_type != "new_task"


def test_debug_log_counts_match_new_task_rows(caplog) -> None:
    baseline = _plan([_task(1, "Kickoff", wbs="1"), _task(2, "Build", wbs="2")])
    current = _plan(
        [
            _task(1, "Kickoff", wbs="1"),
            _task(2, "Build", wbs="2"),
            _task(3, "Extra Workshop", wbs="3"),
        ]
    )
    with caplog.at_level(logging.INFO, logger="app.wsr.new_tasks"):
        mapping = build_new_task_mapping(current, baseline)
    text = caplog.text
    assert "Baseline MPP total tasks: 2" in text
    assert "Current MPP total tasks: 3" in text
    assert "Matched existing tasks: 2" in text
    assert "New tasks detected: 1" in text
    assert "Delay Mapping new-task rows: 1" in text
    assert "NEW TASK:" in text
    assert "Task Name: Extra Workshop" in text
    assert "Reason: Not found in Baseline MPP" in text
    assert mapping.new_task_count == len(mapping.rows) == 1


def test_row_columns_come_from_current_mpp() -> None:
    baseline = _plan([_task(1, "Kickoff", wbs="1")])
    current = _plan(
        [
            _task(1, "Kickoff", wbs="1"),
            _task(
                2,
                "Client Review Meeting",
                wbs="2",
                scheduled_start="2026-09-10",
                scheduled_finish="2026-09-12",
                baseline_finish="2026-09-11",
                predecessor_names=["Kickoff"],
                predecessor_ids=[1],
            ),
        ]
    )
    row = build_new_task_mapping(current, baseline).rows[0]
    assert row.current_task_id == 2
    assert row.name == "Client Review Meeting"
    assert row.wbs == "2"
    assert row.revised_start == "2026-09-10"
    assert row.revised_finish == "2026-09-12"
    assert row.planned_finish == "2026-09-11"
    assert row.predecessor_names == ["Kickoff"]
    assert row.task_type == "new_task"
    assert row.source == "Current MPP"

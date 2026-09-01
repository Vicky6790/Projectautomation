from app.models import PlanTaskData, ProjectPlanData
from app.wsr.delay_engine import baseline_finish_is_na, build_delay_mapping
from app.wsr.facts import derive_wsr_facts


def _plan(tasks: list[PlanTaskData], **kwargs) -> ProjectPlanData:
    return ProjectPlanData(name="Core Banking", owner="Priya Shah", tasks=tasks, **kwargs)


def _mapping(tasks: list[PlanTaskData], **kwargs):
    return derive_wsr_facts(
        _plan(tasks, **kwargs),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    ).delay_mapping


def test_example_na_tasks_are_copied_to_delay_sheet() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=10,
                name="IA Creation",
                wbs="1.1",
                scheduled_start="2026-08-01",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-12",
            ),
            PlanTaskData(
                id=11,
                name="UX Approach",
                wbs="1.2",
                scheduled_start="2026-08-11",
                baseline_finish="NA",
                scheduled_finish="2026-08-18",
            ),
            PlanTaskData(
                id=12,
                name="UX Review",
                wbs="1.3",
                scheduled_start="2026-08-19",
                baseline_finish="2026-08-25",
                scheduled_finish="2026-08-28",
            ),
            PlanTaskData(
                id=13,
                name="Client Approval",
                wbs="1.4",
                scheduled_start="2026-08-29",
                baseline_finish="NA",
                scheduled_finish="2026-09-05",
            ),
            PlanTaskData(
                id=14,
                name="UI Design",
                wbs="1.5",
                scheduled_start="2026-09-06",
                baseline_finish="2026-09-15",
                scheduled_finish="2026-09-18",
            ),
        ]
    )
    assert mapping.current_task_count == 5
    assert mapping.additional_task_count == 2
    assert [row.current_task_id for row in mapping.rows] == [11, 13]
    assert [row.name for row in mapping.rows] == ["UX Approach", "Client Approval"]
    assert [row.planned_finish for row in mapping.rows] == ["NA", "NA"]
    assert len(mapping.rows) == mapping.additional_task_count
    for row in mapping.rows:
        assert baseline_finish_is_na(row.planned_finish)


def test_na_tokens_n_slash_a_and_n_dot_a_are_included() -> None:
    mapping = _mapping(
        [
            PlanTaskData(id=1, name="A", baseline_finish="N/A"),
            PlanTaskData(id=2, name="B", baseline_finish="N.A."),
            PlanTaskData(id=3, name="C", baseline_finish="  na  "),
        ]
    )
    assert [row.current_task_id for row in mapping.rows] == [1, 2, 3]
    assert mapping.additional_task_count == 3
    assert len(mapping.rows) == 3


def test_blank_and_null_baseline_finish_are_not_na() -> None:
    mapping = _mapping(
        [
            PlanTaskData(id=1, name="Blank", baseline_finish=""),
            PlanTaskData(id=2, name="Spaces", baseline_finish="   "),
            PlanTaskData(id=3, name="Missing", baseline_finish=None),
            PlanTaskData(id=4, name="Dated", baseline_finish="2026-08-10"),
        ]
    )
    assert mapping.rows == []
    assert mapping.current_task_count == 4
    assert mapping.additional_task_count == 0


def test_summary_and_milestone_with_na_are_included() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Phase",
                is_summary=True,
                baseline_finish="NA",
                scheduled_start="2026-08-01",
                scheduled_finish="2026-08-20",
            ),
            PlanTaskData(
                id=2,
                name="Gate",
                is_milestone=True,
                baseline_finish="N/A",
            ),
        ]
    )
    assert [row.name for row in mapping.rows] == ["Phase", "Gate"]


def test_delay_sheet_does_not_compare_finish_to_baseline() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Late but baselined",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-09-01",
            ),
            PlanTaskData(
                id=2,
                name="NA task",
                baseline_finish="NA",
                scheduled_finish="2026-08-10",
            ),
        ]
    )
    assert [row.name for row in mapping.rows] == ["NA task"]
    assert mapping.rows[0].shift_days is None
    assert mapping.rows[0].go_live_impact_days is None


def test_parser_keeps_na_text_and_does_not_treat_blank_as_na() -> None:
    from app.mpp.reader import _baseline_finish_value

    class NaField:
        def getBaselineFinish(self):
            return " N/A "

    class DatedField:
        def getBaselineFinish(self):
            return "2026-08-10T17:00:00"

    class BlankField:
        def getBaselineFinish(self):
            return None

    assert _baseline_finish_value(NaField()) == "N/A"
    assert _baseline_finish_value(DatedField()) == "2026-08-10"
    assert _baseline_finish_value(BlankField()) is None


def test_every_sheet_row_has_na_baseline_finish() -> None:
    mapping = build_delay_mapping(
        _plan(
            [
                PlanTaskData(id=1, name="Keep", baseline_finish="NA"),
                PlanTaskData(id=2, name="Skip date", baseline_finish="2026-08-01"),
                PlanTaskData(id=3, name="Skip blank", baseline_finish=None),
                PlanTaskData(id=4, name="Keep slash", baseline_finish="n/a"),
            ]
        ),
        __import__("datetime").date(2026, 8, 22),
        [],
        None,
    )
    assert mapping.current_task_count == 4
    assert mapping.additional_task_count == 2
    assert len(mapping.rows) == 2
    for row in mapping.rows:
        assert baseline_finish_is_na(row.planned_finish)
    assert {row.current_task_id for row in mapping.rows} == {1, 4}

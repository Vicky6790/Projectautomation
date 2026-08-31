from datetime import date

from app.models import PlanAssignmentData, PlanTaskData, ProjectPlanData
from app.wsr.delay_engine import match_task
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


def _mapping(tasks: list[PlanTaskData], baseline: list[PlanTaskData] | None = None, **kwargs):
    from app.wsr.delay_engine import build_delay_mapping

    current = _plan(tasks, **kwargs)
    if baseline is None:
        return derive_wsr_facts(current, "2026-08-22", generated_at="2026-08-22T10:00:00Z").delay_mapping
    return build_delay_mapping(
        current,
        date(2026, 8, 22),
        [],
        date(2026, 9, 1),
        baseline_plan=_plan(baseline, **kwargs),
    )


def test_unchanged_task_is_not_listed() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(),
        ]
    )
    assert mapping.rows == []
    assert mapping.unchanged_task_count == 1
    assert mapping.actual_shift_working_days == 8


def test_finish_after_baseline_is_delay() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-13",
                assignments=_owners("Idealake"),
                predecessor_ids=[],
            ),
            _go_live(id=2, predecessor_ids=[1]),
        ]
    )
    assert [row.name for row in mapping.rows] == ["Design Sign-off"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 3
    assert mapping.rows[0].owner == "Idealake"
    assert mapping.rows[0].planned_finish == "2026-08-10"
    assert mapping.rows[0].revised_finish == "2026-08-13"
    assert mapping.rows[0].evidence_reason
    assert "later" in (mapping.rows[0].evidence_reason or "").casefold()


def test_ahead_task_is_not_listed() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-08",
            ),
            _go_live(),
        ]
    )
    assert mapping.rows == []
    assert mapping.ahead_task_count == 1


def test_additional_is_current_only() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=4,
                name="Additional UX Research",
                scheduled_start="2026-08-12",
                scheduled_finish="2026-08-16",
                assignments=_owners("Idealake"),
                predecessor_ids=[1],
            ),
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(id=90, predecessor_ids=[4], scheduled_finish="2026-08-27"),
        ],
        baseline=[
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(id=90, scheduled_finish="2026-08-20", baseline_finish="2026-08-20"),
        ],
    )
    assert [row.name for row in mapping.rows] == ["Additional UX Research"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days is None
    assert mapping.rows[0].planned_finish is None
    assert mapping.rows[0].go_live_impact_days == 3
    assert mapping.removed_task_count == 0


def test_removed_is_baseline_only() -> None:
    mapping = _mapping(
        [_go_live(scheduled_finish="2026-08-20")],
        baseline=[
            PlanTaskData(
                id=1,
                name="Old discovery",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(scheduled_finish="2026-08-20"),
        ],
    )
    assert mapping.rows == []
    assert mapping.removed_task_count == 1
    assert mapping.removed_rows[0].name == "Old discovery"
    assert mapping.removed_rows[0].task_type == "removed"


def test_matched_without_baseline_finish_is_unavailable() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Review",
                scheduled_finish="2026-08-13",
            ),
            _go_live(),
        ]
    )
    assert mapping.rows == []
    names = [row.name for row in mapping.rows]
    assert "Review" not in names


def test_delayed_task_with_float_has_zero_go_live_impact() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Side documentation",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-15",
                total_slack_days=10,
                critical=False,
            ),
            _go_live(id=2, predecessor_ids=[1]),
        ]
    )
    assert [row.name for row in mapping.rows] == ["Side documentation"]
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 4
    assert mapping.rows[0].go_live_impact_days == 0


def test_delayed_task_on_go_live_path_has_impact() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                baseline_finish="2026-08-20",
                scheduled_finish="2026-09-01",
                critical=True,
                total_slack_days=0,
                assignments=_owners("Idealake"),
            ),
            _go_live(id=2, predecessor_ids=[1]),
        ]
    )
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 8
    assert mapping.rows[0].go_live_impact_days == 8
    assert mapping.actual_shift_working_days == 8


def test_additional_off_path_has_zero_go_live_impact() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            PlanTaskData(
                id=4,
                name="Side analysis",
                scheduled_start="2026-08-21",
                scheduled_finish="2026-08-27",
            ),
            _go_live(id=3, predecessor_ids=[1], scheduled_finish="2026-08-27"),
        ],
        baseline=[
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(id=3, scheduled_finish="2026-08-20", baseline_finish="2026-08-20"),
        ],
    )
    assert [row.name for row in mapping.rows] == ["Side analysis"]
    assert mapping.rows[0].task_type == "additional"
    assert mapping.rows[0].shift_days is None
    assert mapping.rows[0].go_live_impact_days == 0


def test_weekend_inside_shift_period_is_not_counted() -> None:
    mapping = _mapping([_go_live()])
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


def test_repeated_names_in_different_sets_stay_separate() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Creation Of Wireframe",
                wbs="1.1.1",
                set_name="Set 1",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-13",
            ),
            PlanTaskData(
                id=2,
                name="Creation Of Wireframe",
                wbs="1.1.2",
                set_name="Set 2",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(id=3),
        ]
    )
    assert [row.current_task_id for row in mapping.rows] == [1]
    assert mapping.rows[0].shift_days == 3


def test_inserted_row_still_matches_by_id() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                wbs="1.2",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-13",
            ),
            PlanTaskData(
                id=9,
                name="Inserted review",
                wbs="1.3",
                scheduled_start="2026-08-11",
                scheduled_finish="2026-08-12",
            ),
            _go_live(id=3, predecessor_ids=[1]),
        ],
        baseline=[
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                wbs="1.1",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            _go_live(id=3, scheduled_finish="2026-08-20", baseline_finish="2026-08-20"),
        ],
    )
    by_name = {row.name: row for row in mapping.rows}
    assert by_name["Design Sign-off"].task_type == "delay"
    assert by_name["Design Sign-off"].shift_days == 3
    assert by_name["Inserted review"].task_type == "additional"
    assert by_name["Inserted review"].shift_days is None


def test_ambiguous_mapping_requires_validation() -> None:
    from app.wsr.delay_engine import _baseline_index, build_delay_mapping
    from app.wsr.facts import parse_date

    current = PlanTaskData(id=99, name="Review", wbs="", outline_level=3)
    baseline_tasks = [
        PlanTaskData(id=1, name="Review", wbs="1.1.1", outline_level=3, baseline_finish="2026-08-01"),
        PlanTaskData(id=2, name="Review", wbs="1.2.1", outline_level=3, baseline_finish="2026-08-01"),
    ]
    index = _baseline_index(baseline_tasks, [current], parse_date=parse_date)
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
    assert mapping.ambiguous_task_count == 1
    assert mapping.review_rows[0].calculation_status == "ambiguous_match"


def test_chain_delays_do_not_double_count_go_live_impact() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Wireframes",
                baseline_finish="2026-08-20",
                scheduled_finish="2026-08-25",
                critical=True,
                total_slack_days=0,
            ),
            PlanTaskData(
                id=2,
                name="Sign-Off",
                baseline_finish="2026-08-25",
                scheduled_finish="2026-09-01",
                predecessor_ids=[1],
                critical=True,
                total_slack_days=0,
            ),
            _go_live(id=3, predecessor_ids=[2]),
        ]
    )
    by_name = {row.name: row for row in mapping.rows}
    assert by_name["Wireframes"].shift_days == 3
    assert by_name["Sign-Off"].shift_days == 5
    assert (by_name["Wireframes"].go_live_impact_days or 0) + (
        by_name["Sign-Off"].go_live_impact_days or 0
    ) == mapping.actual_shift_working_days == 8


def test_go_live_shifted_by_working_days() -> None:
    mapping = _mapping([_go_live()])
    assert mapping.baseline_go_live == "2026-08-20"
    assert mapping.current_go_live == "2026-09-01"
    assert mapping.actual_shift_working_days == 8


def test_no_go_live_shift() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-13",
            ),
            _go_live(baseline_finish="2026-09-01", scheduled_finish="2026-09-01"),
        ]
    )
    assert mapping.actual_shift_working_days == 0
    assert mapping.rows[0].task_type == "delay"
    assert mapping.rows[0].shift_days == 3
    assert mapping.rows[0].go_live_impact_days == 0


def test_go_live_milestone_is_excluded_from_rows() -> None:
    mapping = _mapping([_go_live()])
    assert mapping.rows == []
    assert mapping.actual_shift_working_days == 8


def test_missing_baseline_go_live() -> None:
    mapping = _mapping(
        [
            PlanTaskData(id=1, name="Design Sign-off", scheduled_finish="2026-08-13"),
            PlanTaskData(id=2, name="Go Live", is_milestone=True, scheduled_finish="2026-09-01"),
        ]
    )
    assert mapping.baseline_go_live is None
    assert mapping.actual_shift_working_days is None
    assert mapping.go_live_status == "unavailable"


def test_ownerless_delay_stays_without_invented_owner() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                baseline_finish="2026-08-20",
                scheduled_finish="2026-09-01",
            ),
            _go_live(id=2, predecessor_ids=[1]),
        ]
    )
    assert mapping.rows[0].owner is None


def test_actual_finish_is_used_when_present() -> None:
    mapping = _mapping(
        [
            PlanTaskData(
                id=1,
                name="CMS Integration",
                baseline_finish="2026-08-20",
                scheduled_finish="2026-08-20",
                actual_finish="2026-09-01",
                critical=True,
                total_slack_days=0,
            ),
            _go_live(id=2, predecessor_ids=[1]),
        ]
    )
    assert mapping.rows[0].revised_finish == "2026-09-01"
    assert mapping.rows[0].shift_days == 8


def test_on_time_task_is_not_listed() -> None:
    mapping = _mapping(
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
    )
    assert mapping.rows == []

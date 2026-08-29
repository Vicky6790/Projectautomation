from datetime import date

from app.models import PlanAssignmentData, PlanPhaseData, PlanResourceData, PlanTaskData, ProjectPlanData
from app.wsr.facts import derive_wsr_facts


def _plan(
    tasks: list[PlanTaskData],
    *,
    phases: list[PlanPhaseData] | None = None,
    resources: list[PlanResourceData] | None = None,
) -> ProjectPlanData:
    return ProjectPlanData(
        name="Core Banking",
        owner="Priya Shah",
        tasks=tasks,
        phases=phases or [],
        resources=resources or [],
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
    assert facts.timeline is not None
    assert facts.timeline[0].name == "Build"
    assert facts.timeline[0].planned_start is None
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


def test_team_capacity_uses_actual_versus_planned_work() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Build",
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-08-20",
                    assignments=[
                        PlanAssignmentData(
                            resource_name="Asha",
                            planned_work_hours=40,
                            actual_work_hours=10,
                        )
                    ],
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
    assert facts.capacity_utilization == 25.0
    assert facts.people_planned == 1


def test_team_capacity_unavailable_without_planned_work() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-01",
                )
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.capacity_utilization is None


def test_phase_status_includes_all_nested_phases_with_child_dates() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Programme", outline_level=1, is_summary=True),
                PlanTaskData(id=2, name="UX", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=3,
                    name="Research",
                    outline_level=3,
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-08-10",
                    percent_complete=100,
                ),
                PlanTaskData(id=4, name="UI", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=5,
                    name="Screens",
                    outline_level=3,
                    scheduled_start="2026-08-11",
                    scheduled_finish="2026-08-31",
                    percent_complete=40,
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [phase.name for phase in facts.phase_statuses]
    assert names == ["UX", "UI"]
    assert facts.phase_statuses[0].planned_start is None
    assert facts.phase_statuses[0].planned_finish is None
    assert facts.phase_statuses[0].actual_start == "2026-08-01"
    assert facts.phase_statuses[0].actual_finish == "2026-08-10"
    assert facts.phase_statuses[1].actual_start == "2026-08-11"
    assert facts.phase_statuses[1].actual_finish == "2026-08-31"


def test_phase_planned_end_uses_baseline_finish_and_deviation_uses_finish() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Programme", outline_level=1, is_summary=True),
                PlanTaskData(id=2, name="UX", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=3,
                    name="Research",
                    outline_level=3,
                    baseline_start="2026-08-01",
                    baseline_finish="2026-08-10",
                    scheduled_start="2026-08-03",
                    scheduled_finish="2026-08-18",
                    percent_complete=40,
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    phase = facts.phase_statuses[0]
    assert phase.planned_start == "2026-08-01"
    assert phase.planned_finish == "2026-08-10"
    assert phase.actual_start == "2026-08-03"
    assert phase.actual_finish == "2026-08-18"


def test_person_days_and_deviated_window_come_from_plan() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Programme", outline_level=1, is_summary=True),
                PlanTaskData(id=2, name="UX", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=3,
                    name="Research",
                    outline_level=3,
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-08-10",
                    actual_start="2026-08-02",
                    actual_finish="2026-08-12",
                    planned_work_hours=16,
                    percent_complete=100,
                ),
                PlanTaskData(
                    id=4,
                    name="Copy",
                    outline_level=3,
                    scheduled_start="2026-08-05",
                    scheduled_finish="2026-08-08",
                    assignments=[
                        PlanAssignmentData(
                            resource_id=1,
                            resource_name="Asha",
                            planned_work_hours=24,
                        )
                    ],
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.person_days_planned == 5.0
    assert facts.phase_statuses[0].actual_start == "2026-08-01"
    assert facts.phase_statuses[0].actual_finish == "2026-08-10"


def test_children_of_project_named_parent_are_all_phases() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Core Banking", outline_level=0, is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Project Plan Phase",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-07-27",
                    scheduled_finish="2026-08-14",
                ),
                PlanTaskData(
                    id=3,
                    name="Prepare plan",
                    outline_level=2,
                    scheduled_start="2026-07-27",
                    scheduled_finish="2026-08-14",
                ),
                PlanTaskData(
                    id=4,
                    name="UX Phase",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-09-25",
                ),
                PlanTaskData(
                    id=5,
                    name="SEO Phase",
                    outline_level=1,
                    scheduled_start="2026-08-26",
                    scheduled_finish="2026-09-30",
                ),
                PlanTaskData(
                    id=6,
                    name="QA Phase",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-10-01",
                    scheduled_finish="2027-01-29",
                ),
                PlanTaskData(
                    id=7,
                    name="Go Live",
                    outline_level=1,
                    is_milestone=True,
                    scheduled_finish="2027-03-26",
                ),
                PlanTaskData(id=8, name="Other workstream", outline_level=0, is_summary=True),
                PlanTaskData(
                    id=9,
                    name="Should not appear",
                    outline_level=1,
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-08-31",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [phase.name for phase in facts.phase_statuses]
    assert names == ["Project Plan Phase", "UX Phase", "SEO Phase", "QA Phase", "Go Live"]
    assert [phase.name for phase in facts.timeline or []] == names


def test_named_phase_convention_adds_nested_and_skips_other_children() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Core Banking", outline_level=0, is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Kickoff workshop",
                    outline_level=1,
                    scheduled_start="2026-07-01",
                    scheduled_finish="2026-07-02",
                ),
                PlanTaskData(id=3, name="Delivery", outline_level=1, is_summary=True),
                PlanTaskData(
                    id=4,
                    name="UX Phase",
                    outline_level=2,
                    is_summary=True,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-09-25",
                ),
                PlanTaskData(
                    id=5,
                    name="Research",
                    outline_level=3,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-07-15",
                ),
                PlanTaskData(
                    id=6,
                    name="Content Phase (Copy + Images)",
                    outline_level=2,
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-09-15",
                ),
                PlanTaskData(
                    id=7,
                    name="CMS Development Phase",
                    outline_level=2,
                    is_summary=True,
                    scheduled_start="2026-09-02",
                    scheduled_finish="2027-01-15",
                ),
                PlanTaskData(
                    id=8,
                    name="Go Live",
                    outline_level=1,
                    is_milestone=True,
                    scheduled_finish="2027-03-26",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [phase.name for phase in facts.phase_statuses]
    assert names == [
        "UX Phase",
        "Content Phase (Copy + Images)",
        "CMS Development Phase",
        "Go Live",
    ]
    assert [phase.name for phase in facts.timeline or []] == names


def test_wbs_1_x_rows_are_phases_with_row_percent_complete() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Core Banking",
                    wbs="1",
                    outline_level=0,
                    is_summary=True,
                    percent_complete=40,
                ),
                PlanTaskData(
                    id=2,
                    name="Project Plan Phase",
                    wbs="1.1",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-07-27",
                    scheduled_finish="2026-08-14",
                    percent_complete=100,
                ),
                PlanTaskData(
                    id=3,
                    name="Prepare plan",
                    wbs="1.1.1",
                    outline_level=2,
                    percent_complete=100,
                ),
                PlanTaskData(
                    id=4,
                    name="UX Phase",
                    wbs="1.2",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-09-25",
                    percent_complete=62,
                ),
                PlanTaskData(
                    id=5,
                    name="Kickoff workshop",
                    wbs="1.3",
                    outline_level=1,
                    scheduled_start="2026-07-01",
                    scheduled_finish="2026-07-02",
                    percent_complete=0,
                ),
                PlanTaskData(
                    id=6,
                    name="QA Phase",
                    wbs="1.5",
                    outline_level=1,
                    is_summary=True,
                    scheduled_start="2026-10-01",
                    scheduled_finish="2027-01-29",
                    percent_complete=15,
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    phases = facts.phase_statuses
    assert [phase.wbs for phase in phases] == ["1.1", "1.2", "1.3", "1.5"]
    assert [phase.name for phase in phases] == [
        "Project Plan Phase",
        "UX Phase",
        "Kickoff workshop",
        "QA Phase",
    ]
    assert [phase.progress for phase in phases] == [100, 62, 0, 15]
    assert facts.phase_count == 4


def test_resources_deployed_counts_resource_sheet() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Build",
                    scheduled_start="2026-08-01",
                    scheduled_finish="2026-08-20",
                    assignments=[
                        PlanAssignmentData(
                            resource_id=1,
                            resource_name="Asha",
                            planned_work_hours=40,
                            actual_work_hours=8,
                        )
                    ],
                )
            ],
            resources=[
                PlanResourceData(id=1, name="Asha"),
                PlanResourceData(id=2, name="Ravi"),
                PlanResourceData(id=3, name="Meera"),
            ],
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.resources_deployed == 3
    assert facts.people_planned == 1


def test_phase_status_includes_leaf_phases_under_programme_root() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Website Revamp", outline_level=1, is_summary=True),
                PlanTaskData(
                    id=2,
                    name="Project Plan Phase",
                    outline_level=2,
                    is_summary=True,
                    scheduled_start="2026-07-27",
                    scheduled_finish="2026-08-14",
                ),
                PlanTaskData(
                    id=3,
                    name="Prepare plan",
                    outline_level=3,
                    scheduled_start="2026-07-27",
                    scheduled_finish="2026-08-14",
                    percent_complete=80,
                ),
                PlanTaskData(
                    id=4,
                    name="SEO Phase",
                    outline_level=2,
                    scheduled_start="2026-08-26",
                    scheduled_finish="2026-09-30",
                ),
                PlanTaskData(
                    id=5,
                    name="QA Phase",
                    outline_level=2,
                    is_summary=True,
                    scheduled_start="2026-10-01",
                    scheduled_finish="2027-01-29",
                ),
                PlanTaskData(
                    id=6,
                    name="Go Live",
                    outline_level=2,
                    is_milestone=True,
                    scheduled_finish="2027-03-26",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [phase.name for phase in facts.phase_statuses]
    assert names == ["Project Plan Phase", "SEO Phase", "QA Phase", "Go Live"]
    assert [phase.name for phase in facts.timeline or []] == names


def test_phase_status_uses_nested_group_when_plan_has_a_container_root() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Core Banking", outline_level=1, is_summary=True),
                PlanTaskData(id=2, name="UX", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=3,
                    name="Research",
                    outline_level=3,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-09-25",
                ),
                PlanTaskData(id=4, name="UI", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=5,
                    name="Screens",
                    outline_level=3,
                    scheduled_start="2026-06-01",
                    scheduled_finish="2026-10-15",
                ),
                PlanTaskData(id=6, name="HTML", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=7,
                    name="Build",
                    outline_level=3,
                    scheduled_start="2026-09-17",
                    scheduled_finish="2026-11-06",
                ),
                PlanTaskData(id=8, name="CMS", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=9,
                    name="Templates",
                    outline_level=3,
                    scheduled_start="2026-09-02",
                    scheduled_finish="2027-01-15",
                ),
                PlanTaskData(id=10, name="Milestones", outline_level=1, is_summary=True),
                PlanTaskData(
                    id=11,
                    name="Go Live",
                    outline_level=2,
                    is_milestone=True,
                    scheduled_finish="2027-03-26",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert [phase.name for phase in facts.phase_statuses] == ["UX", "UI", "HTML", "CMS"]


def test_generated_plan_keeps_top_level_phases() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="UX", outline_level=1, is_summary=True),
                PlanTaskData(id=2, name="UX research", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=3,
                    name="Interviews",
                    outline_level=3,
                    scheduled_start="2026-06-01",
                    scheduled_finish="2026-06-15",
                ),
                PlanTaskData(id=4, name="UI", outline_level=1, is_summary=True),
                PlanTaskData(id=5, name="UI creation", outline_level=2, is_summary=True),
                PlanTaskData(
                    id=6,
                    name="Screens",
                    outline_level=3,
                    scheduled_start="2026-06-16",
                    scheduled_finish="2026-07-15",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert [phase.name for phase in facts.phase_statuses] == ["UX", "UI"]


def test_progress_to_date_is_current_week_only() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Last month kickoff",
                    scheduled_start="2026-07-01",
                    scheduled_finish="2026-07-02",
                    percent_complete=100,
                    actual_finish="2026-07-02",
                ),
                PlanTaskData(
                    id=2,
                    name="This week build",
                    scheduled_start="2026-08-17",
                    scheduled_finish="2026-08-21",
                    percent_complete=50,
                ),
                PlanTaskData(
                    id=3,
                    name="Next month release",
                    scheduled_start="2026-09-01",
                    scheduled_finish="2026-09-05",
                ),
                PlanTaskData(
                    id=4,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-11",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [item.name for item in facts.progress_to_date]
    assert names == ["This week build"]
    item = facts.progress_to_date[0]
    assert item.scheduled_start == "2026-08-17"
    assert item.scheduled_finish == "2026-08-21"
    assert item.progress == 50


def test_current_week_progress_is_ordered_by_date_then_completion() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Later lower",
                    scheduled_start="2026-08-20",
                    scheduled_finish="2026-08-21",
                    percent_complete=20,
                ),
                PlanTaskData(
                    id=2,
                    name="Earlier lower",
                    scheduled_start="2026-08-17",
                    scheduled_finish="2026-08-18",
                    percent_complete=40,
                ),
                PlanTaskData(
                    id=3,
                    name="Earlier higher",
                    scheduled_start="2026-08-17",
                    scheduled_finish="2026-08-19",
                    percent_complete=90,
                ),
                PlanTaskData(
                    id=4,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-11",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert [item.name for item in facts.progress_to_date] == [
        "Earlier higher",
        "Earlier lower",
        "Later lower",
    ]


def test_upcoming_lists_next_planned_tasks() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(
                    id=1,
                    name="Done kickoff",
                    scheduled_finish="2026-08-01",
                    percent_complete=100,
                    actual_finish="2026-08-01",
                ),
                PlanTaskData(
                    id=2,
                    name="Build screens",
                    scheduled_start="2026-08-25",
                    scheduled_finish="2026-08-28",
                    percent_complete=0,
                ),
                PlanTaskData(
                    id=3,
                    name="Go Live",
                    is_milestone=True,
                    scheduled_finish="2026-09-11",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    names = [item.name for item in facts.upcoming_milestones]
    assert names == ["Build screens"]
    build = facts.upcoming_milestones[0]
    assert build.scheduled_start == "2026-08-25"
    assert build.scheduled_finish == "2026-08-28"


def test_project_name_comes_from_wbs_one() -> None:
    facts = derive_wsr_facts(
        _plan(
            [
                PlanTaskData(id=1, name="Core Banking Portal", wbs="1", is_summary=True),
                PlanTaskData(
                    id=2,
                    name="UX Phase",
                    wbs="1.1",
                    is_summary=True,
                    scheduled_start="2026-06-15",
                    scheduled_finish="2026-09-25",
                ),
                PlanTaskData(
                    id=3,
                    name="Go Live",
                    wbs="1.2",
                    is_milestone=True,
                    scheduled_finish="2026-09-11",
                ),
            ]
        ),
        "2026-08-22",
        generated_at="2026-08-22T10:00:00Z",
    )
    assert facts.project_name == "Core Banking Portal"
    assert facts.countdown_days == (date(2026, 9, 11) - date(2026, 8, 22)).days
    assert facts.planned_go_live_date == "2026-09-11"


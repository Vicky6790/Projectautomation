from app.models import PlanTaskData, ProjectPlanData
from app.wsr.delay_diagnostic import build_delay_mapping_diagnostic, diagnostic_csv


def _plan(tasks: list[PlanTaskData]) -> ProjectPlanData:
    return ProjectPlanData(name="Demo", tasks=tasks)


def test_diagnostic_classifies_without_go_live_impact() -> None:
    current = _plan(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                wbs="1.1.1",
                outline_level=3,
                scheduled_start="2026-08-10",
                scheduled_finish="2026-08-13",
                predecessor_ids=[],
            ),
            PlanTaskData(
                id=2,
                name="Extra review",
                wbs="1.1.2",
                outline_level=3,
                scheduled_start="2026-08-11",
                scheduled_finish="2026-08-12",
            ),
            PlanTaskData(
                id=3,
                name="Kickoff",
                wbs="1.1.3",
                outline_level=3,
                scheduled_finish="2026-08-08",
            ),
        ]
    )
    baseline = _plan(
        [
            PlanTaskData(
                id=1,
                name="Design Sign-off",
                wbs="1.1.1",
                outline_level=3,
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            PlanTaskData(
                id=3,
                name="Kickoff",
                wbs="1.1.3",
                outline_level=3,
                baseline_finish="2026-08-10",
                scheduled_finish="2026-08-10",
            ),
            PlanTaskData(
                id=9,
                name="Dropped workshop",
                wbs="1.1.4",
                outline_level=3,
                baseline_finish="2026-08-09",
                scheduled_finish="2026-08-09",
            ),
        ]
    )
    result = build_delay_mapping_diagnostic(current, baseline)
    by_name = {row.current_task_name: row for row in result.rows}
    assert by_name["Design Sign-off"].classification == "DELAYED"
    assert by_name["Design Sign-off"].match_method == "id"
    assert by_name["Extra review"].classification == "ADDITIONAL"
    assert by_name["Kickoff"].classification == "AHEAD"
    assert result.reconciliation.matched_count == 2
    assert result.reconciliation.additional_count == 1
    assert result.reconciliation.removed_count == 1
    assert result.reconciliation.current_reconciles is True
    assert result.reconciliation.baseline_reconciles is True
    text = diagnostic_csv(result)
    assert "DELAYED" in text
    assert "ADDITIONAL" in text
    assert "Dropped workshop" in text


def test_diagnostic_marks_ambiguous_without_guessing() -> None:
    current = _plan([PlanTaskData(id=99, name="Review", outline_level=3, scheduled_finish="2026-08-13")])
    baseline = _plan(
        [
            PlanTaskData(id=1, name="Review", outline_level=3, baseline_finish="2026-08-01"),
            PlanTaskData(id=2, name="Review", outline_level=3, baseline_finish="2026-08-01"),
        ]
    )
    result = build_delay_mapping_diagnostic(current, baseline)
    assert result.rows[0].classification == "AMBIGUOUS"
    assert result.reconciliation.ambiguous_count == 1
    assert result.reconciliation.current_reconciles is False
    assert result.reconciliation.unmatched_current_tasks

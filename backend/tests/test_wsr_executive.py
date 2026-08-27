from datetime import date

from app.models import PlanTaskData, ProjectPlanData
from app.wsr.detection import upcoming_horizon_days
from app.wsr.executive import fallback_executive_summary, generate_executive_summary, validate_executive_summary
from app.wsr.facts import derive_wsr_facts, work_based_progress
from app.wsr.intelligence import build_executive_summary_input


def _plan(tasks: list[PlanTaskData], name: str = "Retail Banking Portal") -> ProjectPlanData:
    return ProjectPlanData(name=name, owner="Priya Shah", tasks=tasks)


def test_work_progress_uses_leaf_actual_over_planned_not_summary() -> None:
    tasks = [
        PlanTaskData(
            id=1,
            name="UX Phase",
            outline_level=1,
            is_summary=True,
            wbs="1.1",
            planned_work_hours=200,
            actual_work_hours=100,
        ),
        PlanTaskData(
            id=2,
            name="IA Creation",
            outline_level=2,
            wbs="1.1.1",
            planned_work_hours=40,
            actual_work_hours=10,
        ),
        PlanTaskData(
            id=3,
            name="UX Approach",
            outline_level=2,
            wbs="1.1.2",
            planned_work_hours=40,
            actual_work_hours=6,
        ),
    ]
    progress = work_based_progress(tasks)
    assert progress["metric"] == "work"
    assert progress["overall_percent"] == 20.0
    assert progress["planned"] == 80.0
    assert progress["actual"] == 16.0


def test_work_progress_unavailable_without_actual_work() -> None:
    tasks = [
        PlanTaskData(
            id=1,
            name="Build",
            scheduled_start="2026-08-01",
            scheduled_finish="2026-08-20",
            percent_complete=50,
        )
    ]
    progress = work_based_progress(tasks)
    assert progress["metric"] == "unavailable"
    assert progress["overall_percent"] is None
    facts = derive_wsr_facts(_plan(tasks + [
        PlanTaskData(id=2, name="Go Live", is_milestone=True, scheduled_finish="2026-09-01")
    ]), "2026-08-22", generated_at="2026-08-22T10:00:00Z")
    assert facts.overall_progress is None


def test_phase_progress_from_child_leaf_work() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", outline_level=1, is_summary=True, wbs="1"),
            PlanTaskData(id=2, name="UX Phase", outline_level=2, is_summary=True, wbs="1.1"),
            PlanTaskData(
                id=3,
                name="IA Creation",
                outline_level=3,
                wbs="1.1.1",
                planned_work_hours=40,
                actual_work_hours=20,
                percent_complete=100,
                actual_finish="2026-08-11",
                is_milestone=True,
            ),
            PlanTaskData(
                id=4,
                name="UX Approach",
                outline_level=3,
                wbs="1.1.2",
                scheduled_finish="2026-08-10",
                planned_work_hours=40,
                actual_work_hours=4,
            ),
            PlanTaskData(
                id=5,
                name="Go-Live",
                outline_level=2,
                wbs="1.2",
                is_milestone=True,
                scheduled_finish="2026-09-30",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    ux = next(phase for phase in payload["phases"] if phase["name"] == "UX Phase")
    assert ux["percentComplete"] == 30.0
    assert payload["progress"]["metric"] == "work"
    assert payload["progress"]["overallPercent"] == 30.0
    assert payload["project"]["goLiveDate"] == "2026-09-30"
    assert facts.countdown_days == (date(2026, 9, 30) - date(2026, 8, 14)).days
    completed = payload["milestones"]["completed"]
    assert any(item["name"] == "IA Creation" for item in completed)
    assert all("Bank" not in (item.get("evidence") or "") for item in completed)


def test_go_live_uses_detection_markers_not_project_finish(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.wsr_go_live_markers", "cutover,launch")
    plan = _plan(
        [
            PlanTaskData(id=1, name="Build", scheduled_finish="2026-08-20"),
            PlanTaskData(
                id=2,
                name="Production Cutover",
                is_milestone=True,
                scheduled_finish="2026-10-01",
            ),
            PlanTaskData(id=3, name="Project Finish", scheduled_finish="2026-11-01"),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    assert facts.planned_go_live_date == "2026-10-01"
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    assert payload["health"]["goLive"] == "upcoming"


def test_upcoming_milestones_use_configured_horizon(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.wsr_upcoming_days", 7)
    assert upcoming_horizon_days() == 7
    plan = _plan(
        [
            PlanTaskData(
                id=1,
                name="UX Sign-off",
                is_milestone=True,
                scheduled_finish="2026-08-18",
            ),
            PlanTaskData(
                id=2,
                name="Go-Live",
                is_milestone=True,
                scheduled_finish="2026-09-30",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    names = [item["name"] for item in payload["milestones"]["upcoming"]]
    assert "UX Sign-off" in names
    assert "Go-Live" not in names


def test_related_overdue_work_is_one_executive_risk() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="UI screens", scheduled_finish="2026-08-01"),
            PlanTaskData(id=2, name="HTML build", scheduled_finish="2026-08-02"),
            PlanTaskData(id=3, name="Frontend integration", scheduled_finish="2026-08-03"),
            PlanTaskData(id=4, name="QA cycle", scheduled_finish="2026-08-04"),
            PlanTaskData(
                id=5,
                name="Go-Live",
                is_milestone=True,
                scheduled_finish="2026-09-01",
                predecessor_ids=[3],
                predecessor_names=["Frontend integration"],
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    overdue_risks = [risk for risk in payload["risks"] if risk["id"] == "r1-overdue"]
    assert len(overdue_risks) == 1
    assert len(overdue_risks[0]["evidence"]) >= 2
    assert all(risk.get("evidence") for risk in payload["risks"])


def test_fallback_summary_does_not_invent_signoff_or_stakeholders() -> None:
    payload = {
        "project": {
            "name": "Retail Banking Portal",
            "asOfDate": "2026-08-14",
            "goLiveDate": "2026-09-30",
            "startDate": "2026-07-01",
            "phaseCount": 2,
        },
        "progress": {"metric": "unavailable", "overallPercent": None},
        "phases": [{"name": "UX Phase", "percentComplete": None, "status": "at-risk"}],
        "milestones": {
            "completed": [
                {
                    "name": "IA Creation",
                    "actualDate": "2026-08-11",
                    "evidence": "Actual finish 2026-08-11; Percent complete 100",
                }
            ],
            "upcoming": [{"name": "UX Approach", "plannedDate": "2026-08-18", "daysToMilestone": 4}],
            "overdue": [],
        },
        "risks": [
            {
                "id": "r3-dependency",
                "title": "UX dependency risk",
                "severity": "high",
                "evidence": ["UX Approach is incomplete", "UI activities depend on UX completion"],
                "goLiveImpact": True,
                "recommendedMitigation": "Prioritize UX review and establish a defined approval turnaround.",
            }
        ],
        "health": {"overall": "at-risk"},
    }
    summary = fallback_executive_summary(payload)
    text = summary.summary.lower()
    assert "the bank" not in text
    assert "signed off" not in text
    assert "progress is unavailable from plan data" in text
    assert "ia creation completed on 2026-08-11" in text
    assert summary.recommended_actions
    assert all(item.source_type == "ai-recommendation" for item in summary.recommended_actions)


def test_invalid_ai_payload_is_rejected() -> None:
    assert validate_executive_summary({"summary": ""}) is None
    assert validate_executive_summary("plain text") is None
    parsed = validate_executive_summary(
        {
            "summary": "Retail Banking Portal is in UX.",
            "highlights": [{"title": "Progress", "description": "Unavailable from plan data", "sourceType": "calculation"}],
            "currentFocus": [{"title": "UX Approach", "description": "Due in 4 days"}],
            "executiveRisks": [{"title": "UX dependency", "description": "UX Approach is incomplete", "severity": "high"}],
            "recommendedActions": [{"action": "Prioritize UX review", "reason": "Downstream UI depends on UX"}],
        }
    )
    assert parsed is not None
    assert parsed.highlights[0].source_type == "calculation"
    assert parsed.recommended_actions[0].source_type == "ai-recommendation"


def test_stub_generation_uses_fallback(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ai_stub", True)
    summary = generate_executive_summary(
        {
            "project": {"name": "Demo", "asOfDate": "2026-08-14"},
            "progress": {"metric": "unavailable"},
            "phases": [],
            "milestones": {"completed": [], "upcoming": [], "overdue": []},
            "risks": [],
            "health": {"overall": "unavailable"},
        }
    )
    assert "Demo" in summary.summary
    assert "unavailable from plan data" in summary.summary.lower()

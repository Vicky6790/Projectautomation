from datetime import date

from app.models import PlanAssignmentData, PlanTaskData, ProjectPlanData
from app.wsr.detection import upcoming_horizon_days
from app.wsr.evidence import items_from_situation_risks
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


def test_phase_progress_from_work_complete_column() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", outline_level=1, is_summary=True, wbs="1"),
            PlanTaskData(
                id=2,
                name="UX Phase",
                outline_level=2,
                is_summary=True,
                wbs="1.1",
                percent_work_complete=30,
            ),
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
    overdue_risks = [
        risk for risk in payload["risks"] if risk["title"] == "Project/Go-Live Impact"
    ]
    assert len(overdue_risks) >= 1
    assert all(
        risk.get("recommendedMitigation")
        for risk in payload["risks"]
        if risk.get("kind") != "focus"
    )
    cards = items_from_situation_risks(plan, payload["risks"])
    assert cards
    assert any("Project/Go-Live Impact" in item.content for item in cards)
    assert all(
        "Mitigation:" in item.content or item.content.startswith("Focus Areas:")
        for item in cards
    )


def test_risk_cards_name_phase_parent_and_task() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Core Banking", wbs="1", outline_level=1, is_summary=True),
            PlanTaskData(id=2, name="UI Phase", wbs="1.3", outline_level=2, is_summary=True),
            PlanTaskData(id=3, name="Screens", wbs="1.3.1", outline_level=3, is_summary=True),
            PlanTaskData(
                id=4,
                name="Homepage layout",
                wbs="1.3.1.1",
                outline_level=4,
                scheduled_finish="2026-08-01",
            ),
            PlanTaskData(
                id=5,
                name="Go-Live",
                wbs="1.9",
                outline_level=2,
                is_milestone=True,
                scheduled_finish="2026-09-01",
                predecessor_ids=[4],
                predecessor_names=["Homepage layout"],
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    cards = items_from_situation_risks(plan, payload["risks"])
    assert cards
    assert any("UI Phase / Screens" in item.content for item in cards)
    assert any("Mitigation:" in item.content for item in cards)
    assert all("Homepage layout" not in item.content for item in cards)
    assert all("Affected task:" not in item.content for item in cards)
    overdue = next(
        risk for risk in payload["risks"] if risk["title"] == "Project/Go-Live Impact"
    )
    assert "UI Phase / Screens / Homepage layout" in overdue["evidence"][0]


def test_completed_tasks_are_not_listed_as_risks() -> None:
    plan = _plan(
        [
            PlanTaskData(
                id=1,
                name="Deck Preparation",
                scheduled_finish="2026-08-01",
                actual_finish="2026-08-28",
                percent_complete=100,
            ),
            PlanTaskData(
                id=2,
                name="Deck Internal Review and Update",
                scheduled_finish="2026-09-05",
                predecessor_ids=[1],
                predecessor_names=["Deck Preparation"],
            ),
            PlanTaskData(
                id=3,
                name="Go-Live",
                is_milestone=True,
                scheduled_finish="2026-09-30",
                predecessor_ids=[2],
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-09-03", generated_at="2026-09-03T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-09-03")
    names = {
        name
        for risk in payload["risks"]
        for name in (risk.get("affectedTasks") or [])
    }
    assert "Deck Preparation" not in names
    cards = items_from_situation_risks(plan, payload["risks"])
    assert all("Deck Preparation" not in item.content for item in cards)


def test_isolated_overdue_with_float_is_not_a_project_risk() -> None:
    plan = _plan(
        [
            PlanTaskData(
                id=1,
                name="Parked documentation",
                scheduled_finish="2026-08-01",
                total_slack_days=20,
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
    names = {
        name
        for risk in payload["risks"]
        for name in (risk.get("affectedTasks") or [])
    }
    assert "Parked documentation" not in names


def test_delayed_task_blocking_milestone_is_a_risk_with_impact_and_action() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="UX Phase", wbs="1.1", outline_level=1, is_summary=True),
            PlanTaskData(
                id=2,
                name="UX sign-off",
                wbs="1.1.1",
                outline_level=2,
                scheduled_finish="2026-08-01",
                assignments=[PlanAssignmentData(resource_name="Priya Shah")],
            ),
            PlanTaskData(
                id=3,
                name="UI screens",
                wbs="1.1.2",
                outline_level=2,
                scheduled_finish="2026-08-20",
                predecessor_ids=[2],
                predecessor_names=["UX sign-off"],
            ),
            PlanTaskData(
                id=4,
                name="UI sign-off",
                wbs="1.1.3",
                outline_level=2,
                is_milestone=True,
                scheduled_finish="2026-09-01",
                predecessor_ids=[3],
                predecessor_names=["UI screens"],
            ),
            PlanTaskData(
                id=5,
                name="Go-Live",
                wbs="1.9",
                outline_level=1,
                is_milestone=True,
                scheduled_finish="2026-10-01",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    ux_risks = [
        risk
        for risk in payload["risks"]
        if risk.get("kind") != "focus" and "UX sign-off" in (risk.get("affectedTasks") or [])
    ]
    assert ux_risks
    risk = ux_risks[0]
    assert risk["title"] in {
        "Current Phase Impact",
        "Milestone Impact",
        "Downstream Phase Impact",
        "Project/Go-Live Impact",
    }
    assert risk["severity"] in {"high", "medium", "low"}
    assert risk.get("projectImpact")
    assert risk.get("recommendedMitigation")
    assert risk.get("owner") == "Priya Shah"
    assert risk.get("targetDate") == "2026-08-01"
    cards = items_from_situation_risks(plan, payload["risks"])
    assert cards
    text = " ".join(item.content for item in cards)
    assert "Impact:" in text
    assert "Mitigation:" in text
    assert "Owner: Priya Shah" in text
    assert "Target Date: 2026-08-01" in text


def test_risk_section_keeps_top_five_material_items() -> None:
    predecessors = [
        PlanTaskData(
            id=index,
            name=f"Path work {index}",
            scheduled_finish="2026-08-01",
        )
        for index in range(1, 8)
    ]
    plan = _plan(
        [
            *predecessors,
            PlanTaskData(
                id=99,
                name="Go-Live",
                is_milestone=True,
                scheduled_finish="2026-09-01",
                predecessor_ids=[item.id for item in predecessors],
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    material = [risk for risk in payload["risks"] if risk.get("kind") != "focus"]
    assert material
    assert len(material) <= 5
    cards = items_from_situation_risks(plan, payload["risks"])
    risk_cards = [item for item in cards if not item.content.startswith("Focus Areas:")]
    assert len(risk_cards) <= 5


def test_future_phase_overdue_is_not_reported_during_current_phase() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", wbs="1", outline_level=1, is_summary=True),
            PlanTaskData(
                id=2,
                name="UX Phase",
                wbs="1.1",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-07-01",
                scheduled_finish="2026-09-15",
                percent_complete=40,
            ),
            PlanTaskData(
                id=3,
                name="UX wireframes",
                wbs="1.1.1",
                outline_level=3,
                scheduled_start="2026-07-01",
                scheduled_finish="2026-08-01",
                percent_complete=40,
                predecessor_ids=[],
            ),
            PlanTaskData(
                id=4,
                name="UX sign-off",
                wbs="1.1.2",
                outline_level=3,
                is_milestone=True,
                scheduled_start="2026-08-02",
                scheduled_finish="2026-08-10",
                percent_complete=0,
                predecessor_ids=[3],
                predecessor_names=["UX wireframes"],
            ),
            PlanTaskData(
                id=5,
                name="UI Phase",
                wbs="1.2",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-08-11",
                scheduled_finish="2026-09-30",
            ),
            PlanTaskData(
                id=6,
                name="UI screens",
                wbs="1.2.1",
                outline_level=3,
                scheduled_start="2026-08-11",
                scheduled_finish="2026-09-01",
                predecessor_ids=[4],
                predecessor_names=["UX sign-off"],
            ),
            PlanTaskData(
                id=7,
                name="CUG",
                wbs="1.3",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-10-20",
            ),
            PlanTaskData(
                id=8,
                name="CUG execution",
                wbs="1.3.1",
                outline_level=3,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-08-01",
            ),
            PlanTaskData(
                id=9,
                name="VAPT",
                wbs="1.4",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-11-01",
                scheduled_finish="2026-11-20",
            ),
            PlanTaskData(
                id=10,
                name="VAPT testing",
                wbs="1.4.1",
                outline_level=3,
                scheduled_start="2026-11-01",
                scheduled_finish="2026-08-01",
            ),
            PlanTaskData(
                id=11,
                name="Go-Live",
                wbs="1.5",
                outline_level=2,
                is_milestone=True,
                scheduled_start="2026-12-01",
                scheduled_finish="2026-12-15",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    names = {
        name
        for risk in payload["risks"]
        if risk.get("kind") != "focus"
        for name in (risk.get("affectedTasks") or [])
    }
    assert "CUG execution" not in names
    assert "VAPT testing" not in names
    assert "Go-Live" not in names
    cards = items_from_situation_risks(plan, payload["risks"])
    text = " ".join(item.content for item in cards)
    assert "CUG is upcoming" not in text
    assert "VAPT" not in text
    assert "Production deployment" not in text
    focus = next((risk for risk in payload["risks"] if risk.get("kind") == "focus"), None)
    assert focus is not None
    focus_text = " ".join(focus.get("evidence") or [])
    assert "UX Phase" in focus_text
    assert "CUG" not in focus_text
    assert "VAPT" not in focus_text


def test_current_phase_delay_can_cite_next_dependent_phase() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", wbs="1", outline_level=1, is_summary=True),
            PlanTaskData(
                id=2,
                name="UX Phase",
                wbs="1.1",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-07-01",
                scheduled_finish="2026-09-01",
                percent_complete=30,
            ),
            PlanTaskData(
                id=3,
                name="UX sign-off",
                wbs="1.1.1",
                outline_level=3,
                is_milestone=True,
                scheduled_start="2026-07-20",
                scheduled_finish="2026-08-01",
                percent_complete=10,
                assignments=[PlanAssignmentData(resource_name="Priya Shah")],
            ),
            PlanTaskData(
                id=4,
                name="UI Phase",
                wbs="1.2",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-08-10",
                scheduled_finish="2026-09-30",
            ),
            PlanTaskData(
                id=5,
                name="UI screens",
                wbs="1.2.1",
                outline_level=3,
                scheduled_start="2026-08-10",
                scheduled_finish="2026-08-25",
                predecessor_ids=[3],
                predecessor_names=["UX sign-off"],
            ),
            PlanTaskData(
                id=6,
                name="CUG",
                wbs="1.3",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-10-20",
            ),
            PlanTaskData(
                id=7,
                name="CUG execution",
                wbs="1.3.1",
                outline_level=3,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-10-20",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    ux_risks = [
        risk
        for risk in payload["risks"]
        if risk.get("kind") != "focus" and "UX sign-off" in (risk.get("affectedTasks") or [])
    ]
    assert ux_risks
    risk = ux_risks[0]
    assert risk["title"] == "Downstream Phase Impact"
    assert "UI" in (risk.get("projectImpact") or "")
    assert "CUG" not in (risk.get("projectImpact") or "")
    names = {
        name
        for item in payload["risks"]
        if item.get("kind") != "focus"
        for name in (item.get("affectedTasks") or [])
    }
    assert "CUG execution" not in names
    focus = next(item for item in payload["risks"] if item.get("kind") == "focus")
    focus_text = " ".join(focus.get("evidence") or [])
    assert "UX Phase" in focus_text
    assert "UI Phase" in focus_text
    assert "CUG" not in focus_text


def test_no_material_current_phase_risk_when_only_future_work_is_open() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", wbs="1", outline_level=1, is_summary=True),
            PlanTaskData(
                id=2,
                name="UX Phase",
                wbs="1.1",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-07-01",
                scheduled_finish="2026-08-10",
                percent_complete=100,
            ),
            PlanTaskData(
                id=3,
                name="UX wireframes",
                wbs="1.1.1",
                outline_level=3,
                scheduled_start="2026-07-01",
                scheduled_finish="2026-08-10",
                percent_complete=100,
                actual_finish="2026-08-10",
            ),
            PlanTaskData(
                id=4,
                name="UI Phase",
                wbs="1.2",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-08-11",
                scheduled_finish="2026-09-01",
                percent_complete=20,
            ),
            PlanTaskData(
                id=5,
                name="UI screens",
                wbs="1.2.1",
                outline_level=3,
                scheduled_start="2026-08-11",
                scheduled_finish="2026-09-01",
                percent_complete=20,
                total_slack_days=15,
            ),
            PlanTaskData(
                id=6,
                name="CUG",
                wbs="1.3",
                outline_level=2,
                is_summary=True,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-10-20",
            ),
            PlanTaskData(
                id=7,
                name="CUG execution",
                wbs="1.3.1",
                outline_level=3,
                scheduled_start="2026-10-01",
                scheduled_finish="2026-08-01",
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    material = [risk for risk in payload["risks"] if risk.get("kind") != "focus"]
    names = {name for risk in material for name in (risk.get("affectedTasks") or [])}
    assert "CUG execution" not in names
    assert "UI screens" not in names
    cards = items_from_situation_risks(plan, material)
    assert cards == []


def test_fallback_summary_is_two_paragraphs_from_plan() -> None:
    plan = _plan(
        [
            PlanTaskData(id=1, name="Retail Banking Portal", outline_level=1, is_summary=True, wbs="1"),
            PlanTaskData(
                id=2,
                name="UX Phase",
                outline_level=2,
                is_summary=True,
                wbs="1.1",
                percent_work_complete=30,
            ),
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
                predecessor_ids=[4],
            ),
        ]
    )
    facts = derive_wsr_facts(plan, "2026-08-14", generated_at="2026-08-14T10:00:00Z")
    payload = build_executive_summary_input(plan, facts, "2026-08-14")
    summary = fallback_executive_summary(payload)
    paragraphs = [part.strip() for part in summary.summary.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2
    assert "progressing across" in paragraphs[0]
    assert "overall work-based progress at 30%" in paragraphs[0]
    assert "UX Phase" in paragraphs[0]
    assert "IA Creation" in paragraphs[0]
    assert "14 August 2026" in paragraphs[0]
    assert "current delivery focus remains on" in paragraphs[1].lower()
    assert "go-live" in paragraphs[1].lower()
    assert "risk" not in summary.summary.lower()
    assert "delay" not in summary.summary.lower()
    assert "behind" not in summary.summary.lower()
    assert "off track" not in summary.summary.lower()
    assert "management attention" not in summary.summary.lower()
    assert "sign-off and sign-off" not in summary.summary.lower()


def test_one_percent_complete_is_not_done() -> None:
    from app.wsr.facts import _complete

    task = PlanTaskData(id=1, name="Sign-Off", percent_complete=1.0, scheduled_finish="2026-08-01")
    assert not _complete(task)


def test_hundred_percent_complete_is_done() -> None:
    from app.wsr.facts import _complete

    task = PlanTaskData(id=1, name="Sign-Off", percent_complete=100, scheduled_finish="2026-08-01")
    assert _complete(task)


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
    paragraphs = [part.strip() for part in summary.summary.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2
    text = summary.summary.lower()
    assert "the bank" not in text
    assert "signed off" not in text
    assert "progress is unavailable" not in text
    assert "ia creation" in text
    assert "ux phase" in paragraphs[0].lower()
    assert "ux approach" in text
    assert "current delivery focus remains on" in paragraphs[1].lower()
    assert "go-live" in paragraphs[1].lower()
    assert "risk" not in text
    assert "delay" not in text
    assert "behind" not in text
    assert "off track" not in text
    assert "management attention" not in text
    assert "project plan sign-off and project plan sign-off" not in text
    assert summary.recommended_actions
    assert all(item.source_type == "ai-recommendation" for item in summary.recommended_actions)


def test_fallback_summary_dedupes_repeated_milestone_names() -> None:
    payload = {
        "project": {"name": "Core Banking", "asOfDate": "2026-09-06", "phaseCount": 4},
        "progress": {"metric": "work", "overallPercent": 42},
        "phases": [{"name": "Project Plan Sign-Off", "percentComplete": 80, "status": "on-track"}],
        "milestones": {
            "completed": [
                {"name": "Project Plan Sign-Off", "actualDate": "2026-08-01"},
                {"name": "Project Plan Sign-Off", "actualDate": "2026-08-02"},
            ],
            "upcoming": [
                {"name": "Sign-Off", "plannedDate": "2026-09-10", "daysToMilestone": 4},
                {"name": "Sign-Off", "plannedDate": "2026-09-12", "daysToMilestone": 6},
            ],
            "overdue": [],
        },
        "risks": [],
        "health": {"overall": "at-risk"},
        "delayMapping": {},
        "dependencies": [],
    }
    summary = fallback_executive_summary(payload)
    text = summary.summary.lower()
    assert "project plan sign-off and project plan sign-off" not in text
    assert "sign-off and sign-off" not in text
    assert "risk" not in text
    paragraphs = [part.strip() for part in summary.summary.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2
    assert validate_executive_summary({"summary": ""}) is None
    assert validate_executive_summary("plain text") is None
    parsed = validate_executive_summary(
        {
            "summary": "Retail Banking Portal is in UX.\n\nImmediate management focus is on UX Approach.",
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
    paragraphs = [part.strip() for part in summary.summary.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2
    assert "unavailable from plan data" not in summary.summary.lower()
    assert "delivery continues in line with the current plan" in paragraphs[1].lower()
    assert "delay" not in summary.summary.lower()
    assert "management attention" not in summary.summary.lower()
    assert "risk" not in summary.summary.lower()

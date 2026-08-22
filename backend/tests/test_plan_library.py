from fastapi.testclient import TestClient

from app.plan import PhaseSelection, PlanConfiguration, expand_plan
from app.plan.library import catalog


def test_catalog_lists_phases_and_set_deliverables() -> None:
    data = catalog()
    ids = [phase["id"] for phase in data["phases"]]
    assert ids == ["discovery", "ux", "ui", "html", "cms", "qa", "uat", "launch"]
    assert "wireframe_creation" in data["set_deliverables"]
    assert "cms" in data["set_deliverables"]


def test_expand_includes_only_selected_deliverables() -> None:
    plan = expand_plan(
        PlanConfiguration(
            phases=[
                PhaseSelection(phase_id="ux", deliverables=["ux_research"]),
                PhaseSelection(
                    phase_id="ui",
                    deliverables=["ui_creation"],
                    set_overrides={"ui_creation": 1},
                ),
            ]
        )
    )
    names = [task.name for task in plan.tasks]
    assert "UX research" in names
    assert "Wireframe creation" not in names
    assert "UI creation" in names
    assert "Brand guidelines (create)" not in names


def test_common_set_count_and_override() -> None:
    plan = expand_plan(
        PlanConfiguration(
            common_set_count=3,
            phases=[
                PhaseSelection(
                    phase_id="ux",
                    deliverables=["wireframe_creation"],
                    set_overrides={"wireframe_creation": 2},
                ),
                PhaseSelection(phase_id="html", deliverables=["html"]),
            ],
        )
    )
    sets = [task.name for task in plan.tasks if task.name.startswith("Set ")]
    assert sets.count("Set 1") == 2
    assert sets.count("Set 2") == 2
    assert sets.count("Set 3") == 1


def test_cms_prereq_once_and_repeated_sets() -> None:
    plan = expand_plan(
        PlanConfiguration(
            common_set_count=2,
            phases=[PhaseSelection(phase_id="cms", deliverables=["cms"])],
        )
    )
    names = [task.name for task in plan.tasks]
    assert names.count("CMS information architecture") == 1
    assert names.count("CMS template build") == 2


def test_omitted_phase_drops_its_dependency() -> None:
    plan = expand_plan(
        PlanConfiguration(
            phases=[
                PhaseSelection(phase_id="ui", deliverables=["ui_creation"]),
                PhaseSelection(phase_id="cms", deliverables=["cms"]),
            ]
        )
    )
    cms = next(task for task in plan.tasks if task.name == "CMS" and task.outline_level == 1)
    ui = next(task for task in plan.tasks if task.name == "UI" and task.outline_level == 1)
    assert ui.id not in cms.predecessor_ids


def test_library_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/plan/library")
    assert response.status_code == 200
    assert "phases" in response.json()

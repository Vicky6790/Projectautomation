from app.models import PlanTaskData, ProjectPlanData
from app.wsr.outline import (
    is_phase_code,
    is_portfolio_code,
    is_project_code,
    parse_outline_code,
)
from app.wsr.projects import split_plan_projects


def test_outline_codes_classify_portfolio_project_phase_and_task() -> None:
    assert parse_outline_code("0") == (0,)
    assert is_portfolio_code("0")
    assert is_project_code("1")
    assert is_project_code("2")
    assert is_phase_code("1.1")
    assert is_phase_code("2.3", project_code="2")
    assert not is_phase_code("2.3", project_code="1")
    assert not is_phase_code("1.1.1")
    assert not is_project_code("0")
    assert not is_portfolio_code("1")


def _multi_plan() -> ProjectPlanData:
    return ProjectPlanData(
        name="Portfolio MPP",
        owner="Alex PM",
        tasks=[
            PlanTaskData(id=1, name="All Accounts", wbs="0", outline_level=0, is_summary=True),
            PlanTaskData(id=2, name="Core Banking", wbs="1", outline_level=1, is_summary=True),
            PlanTaskData(id=3, name="UX Phase", wbs="1.1", outline_level=2, is_summary=True),
            PlanTaskData(id=4, name="Build portal", wbs="1.1.1", outline_level=3),
            PlanTaskData(
                id=5,
                name="Go Live",
                wbs="1.2",
                outline_level=2,
                is_milestone=True,
                scheduled_finish="2026-09-11",
            ),
            PlanTaskData(id=6, name="Payments Hub", wbs="2", outline_level=1, is_summary=True),
            PlanTaskData(id=7, name="API Phase", wbs="2.1", outline_level=2, is_summary=True),
            PlanTaskData(id=8, name="Build API", wbs="2.1.1", outline_level=3),
            PlanTaskData(
                id=9,
                name="Go Live",
                wbs="2.2",
                outline_level=2,
                is_milestone=True,
                scheduled_finish="2026-10-30",
            ),
        ],
    )


def test_split_keeps_single_project_as_one_plan() -> None:
    plan = ProjectPlanData(
        name="Demo",
        tasks=[
            PlanTaskData(id=1, name="Core Banking", wbs="1", is_summary=True),
            PlanTaskData(id=2, name="UX Phase", wbs="1.1", is_summary=True),
            PlanTaskData(id=3, name="Build", wbs="1.1.1"),
        ],
    )
    split = split_plan_projects(plan)
    assert split.portfolio_name is None
    assert len(split.projects) == 1
    assert split.projects[0].code == "1"
    assert split.projects[0].plan is plan


def test_split_multi_project_mpp_excludes_portfolio_parent() -> None:
    split = split_plan_projects(_multi_plan())
    assert split.portfolio_name == "All Accounts"
    assert [item.code for item in split.projects] == ["1", "2"]
    assert [item.name for item in split.projects] == ["Core Banking", "Payments Hub"]
    first_names = [task.name for task in split.projects[0].plan.tasks]
    second_names = [task.name for task in split.projects[1].plan.tasks]
    assert "All Accounts" not in first_names
    assert "All Accounts" not in second_names
    assert first_names == ["Core Banking", "UX Phase", "Build portal", "Go Live"]
    assert second_names == ["Payments Hub", "API Phase", "Build API", "Go Live"]
    assert "Build API" not in first_names
    assert "Build portal" not in second_names

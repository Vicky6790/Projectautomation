"""Split a multi-project MPP into one WSR plan per integer outline code."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import PlanTaskData, ProjectPlanData
from app.wsr.facts import _descendants
from app.wsr.outline import is_portfolio_code, parse_outline_code, project_id


@dataclass(frozen=True)
class PlanProject:
    code: str | None
    name: str | None
    plan: ProjectPlanData


@dataclass(frozen=True)
class PlanProjectSplit:
    portfolio_name: str | None
    projects: list[PlanProject]


def split_plan_projects(plan: ProjectPlanData) -> PlanProjectSplit:
    """One slice per project integer. A single-project file stays one full plan."""

    codes = _project_ids(plan.tasks)
    portfolio = _portfolio_name(plan.tasks)
    if len(codes) <= 1:
        code = str(codes[0]) if codes else None
        return PlanProjectSplit(
            portfolio_name=portfolio,
            projects=[
                PlanProject(
                    code=code,
                    name=_project_name(plan.tasks, code) or plan.name,
                    plan=plan,
                )
            ],
        )
    return PlanProjectSplit(
        portfolio_name=portfolio,
        projects=[_slice_project(plan, code) for code in codes],
    )


def _project_ids(tasks: list[PlanTaskData]) -> list[int]:
    found: set[int] = set()
    for task in tasks:
        ident = project_id(task.wbs)
        if ident is not None:
            found.add(ident)
    return sorted(found)


def _portfolio_name(tasks: list[PlanTaskData]) -> str | None:
    for task in tasks:
        if is_portfolio_code(task.wbs):
            name = (task.name or "").strip()
            if name:
                return name
    return None


def _project_name(tasks: list[PlanTaskData], code: str | None) -> str | None:
    if not code:
        return None
    for task in tasks:
        if parse_outline_code(task.wbs) == parse_outline_code(code):
            name = (task.name or "").strip()
            if name:
                return name
    return None


def _slice_project(plan: ProjectPlanData, code: int) -> PlanProject:
    label = str(code)
    tasks = _tasks_for_project(plan.tasks, code)
    name = _project_name(tasks, label) or _project_name(plan.tasks, label)
    return PlanProject(code=label, name=name or plan.name, plan=_sliced_plan(plan, tasks, name))


def _tasks_for_project(tasks: list[PlanTaskData], code: int) -> list[PlanTaskData]:
    selected: set[int] = set()
    for task in tasks:
        ident = project_id(task.wbs)
        if ident == code:
            selected.add(task.id)
    row = next((task for task in tasks if parse_outline_code(task.wbs) == (code,)), None)
    if row is not None:
        selected.add(row.id)
        for child in _descendants(tasks, row):
            ident = project_id(child.wbs)
            if ident is None or ident == code:
                selected.add(child.id)
    return [task for task in tasks if task.id in selected]


def _sliced_plan(
    plan: ProjectPlanData,
    tasks: list[PlanTaskData],
    name: str | None,
) -> ProjectPlanData:
    assigned_ids = {
        item.resource_id for task in tasks for item in task.assignments if item.resource_id
    }
    assigned_names = {
        item.resource_name for task in tasks for item in task.assignments if item.resource_name
    }
    resources = [
        item
        for item in plan.resources
        if item.id in assigned_ids or item.name in assigned_names
    ]
    if not resources:
        resources = list(plan.resources)
    return plan.model_copy(
        update={
            "name": name or plan.name,
            "tasks": tasks,
            "resources": resources,
            "phases": [],
        }
    )

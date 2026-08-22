from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import GeneratedPlan, GeneratedTask
from app.plan.library import (
    BRAND_GUIDELINE_MODES,
    DELIVERABLE_SEQUENCE,
    PHASE_SEQUENCE,
    PHASES,
    SET_DELIVERABLES,
)


class PhaseSelection(BaseModel):
    phase_id: str
    deliverables: list[str] = Field(default_factory=list)
    set_overrides: dict[str, int] = Field(default_factory=dict)


class PlanConfiguration(BaseModel):
    name: str = "Generated Plan"
    common_set_count: int = 1
    phases: list[PhaseSelection]


def _phase_map() -> dict[str, dict]:
    return {phase["id"]: phase for phase in PHASES}


def _deliverable_map() -> dict[str, dict]:
    return {
        item["id"]: {**item, "phase_id": phase["id"]}
        for phase in PHASES
        for item in phase["deliverables"]
    }


def _set_count(config: PlanConfiguration, selection: PhaseSelection, deliverable_id: str) -> int:
    if deliverable_id not in SET_DELIVERABLES:
        return 1
    return max(selection.set_overrides.get(deliverable_id, config.common_set_count), 1)


def expand_plan(config: PlanConfiguration) -> GeneratedPlan:
    phases = _phase_map()
    by_id = _deliverable_map()
    selected_ids = {
        item_id
        for selection in config.phases
        for item_id in selection.deliverables
        if item_id in by_id and by_id[item_id]["phase_id"] == selection.phase_id
    }
    if BRAND_GUIDELINE_MODES <= selected_ids:
        selected_ids.remove("brand_guidelines_existing")

    tasks: list[GeneratedTask] = []
    next_id = 1
    phase_end: dict[str, int] = {}
    deliverable_end: dict[str, int] = {}

    def add_task(**kwargs) -> GeneratedTask:
        nonlocal next_id
        task = GeneratedTask(id=next_id, **kwargs)
        tasks.append(task)
        next_id += 1
        return task

    for selection in config.phases:
        phase = phases.get(selection.phase_id)
        if phase is None:
            continue
        chosen = [
            item for item in phase["deliverables"] if item["id"] in selected_ids
        ]
        phase_task = add_task(name=phase["name"], outline_level=1, is_summary=True)
        last_leaf: int | None = None
        for item in chosen:
            preds = [
                deliverable_end[source]
                for source, target in DELIVERABLE_SEQUENCE
                if target == item["id"] and source in deliverable_end
            ]
            deliverable_task = add_task(
                name=item["name"],
                outline_level=2,
                is_summary=True,
                predecessor_ids=preds,
            )
            last_leaf = deliverable_task.id
            for name in item.get("prereq_tasks", []):
                last_leaf = add_task(
                    name=name,
                    outline_level=3,
                    predecessor_ids=[last_leaf],
                ).id
            for name in item.get("prereq_milestones", []):
                last_leaf = add_task(
                    name=name,
                    outline_level=3,
                    is_milestone=True,
                    predecessor_ids=[last_leaf],
                ).id
            if item["set_based"]:
                for index in range(1, _set_count(config, selection, item["id"]) + 1):
                    set_task = add_task(
                        name=f"Set {index}",
                        outline_level=3,
                        is_summary=True,
                        set_name=f"Set {index}",
                        predecessor_ids=[last_leaf],
                    )
                    last_leaf = set_task.id
                    for name in item["tasks"]:
                        last_leaf = add_task(
                            name=name,
                            outline_level=4,
                            set_name=f"Set {index}",
                            predecessor_ids=[last_leaf],
                        ).id
                    for name in item["milestones"]:
                        last_leaf = add_task(
                            name=name,
                            outline_level=4,
                            is_milestone=True,
                            set_name=f"Set {index}",
                            predecessor_ids=[last_leaf],
                        ).id
            else:
                for name in item["tasks"]:
                    last_leaf = add_task(
                        name=name,
                        outline_level=3,
                        predecessor_ids=[last_leaf],
                    ).id
                for name in item["milestones"]:
                    last_leaf = add_task(
                        name=name,
                        outline_level=3,
                        is_milestone=True,
                        predecessor_ids=[last_leaf],
                    ).id
            deliverable_end[item["id"]] = last_leaf or deliverable_task.id
        phase_end[phase["id"]] = last_leaf or phase_task.id

    phase_summaries = {
        phase_id: next(
            task
            for task in tasks
            if task.outline_level == 1 and task.name == phases[phase_id]["name"]
        )
        for phase_id in phase_end
    }
    for source, target in PHASE_SEQUENCE:
        if source in phase_end and target in phase_summaries:
            target_task = phase_summaries[target]
            pred = phase_end[source]
            if pred not in target_task.predecessor_ids:
                target_task.predecessor_ids.append(pred)

    valid_ids = {task.id for task in tasks}
    for task in tasks:
        task.predecessor_ids = [
            pred for pred in task.predecessor_ids if pred in valid_ids and pred != task.id
        ]
    return GeneratedPlan(name=config.name, tasks=tasks)

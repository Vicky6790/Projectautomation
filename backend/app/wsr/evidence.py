from __future__ import annotations

import uuid

from app.models import AiDerivedItem, EvidenceReference, PlanTaskData, ProjectPlanData

AI_SECTIONS = (
    "client_needs",
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
)

_SECTION_LABEL = {
    "client_needs": "client_need",
    "risks": "risk_or_focus_area",
    "issues": "issue",
    "dependencies": "dependency",
    "management_attention": "management_attention",
    "decisions_required": "decision_required",
    "next_7_day_priorities": "next_seven_day_priority",
}


def evidence_catalog(plan: ProjectPlanData) -> list[dict]:
    rows: list[dict] = []
    for task in plan.tasks:
        if task.is_summary:
            continue
        rows.append(
            {
                "name": task.name,
                "date": task.scheduled_finish or task.scheduled_start or task.baseline_finish,
                "progress": task.percent_complete,
                "is_milestone": task.is_milestone,
                "gate": task.gate,
                "predecessors": task.predecessor_names,
                "resources": [item.resource_name for item in task.assignments],
            }
        )
    return rows


def reference_for(task: PlanTaskData) -> EvidenceReference:
    resources = [item.resource_name for item in task.assignments] or None
    predecessors = task.predecessor_names or None
    return EvidenceReference(
        task_or_milestone_name=task.name,
        date=task.scheduled_finish or task.scheduled_start,
        progress=task.percent_complete,
        predecessor_names=predecessors,
        resource_assignments=resources,
        dependency_description=(
            None if not predecessors else f"Depends on {', '.join(predecessors)}"
        ),
    )


def resolve_item(
    plan: ProjectPlanData,
    section: str,
    content: str,
    names: list[str],
) -> AiDerivedItem | None:
    lookup = {task.name.lower(): task for task in plan.tasks if task.name}
    evidence: list[EvidenceReference] = []
    for name in names:
        task = lookup.get(name.lower().strip())
        if task is None:
            continue
        evidence.append(reference_for(task))
    if not evidence or not content.strip():
        return None
    return AiDerivedItem(
        id=str(uuid.uuid4()),
        section=_SECTION_LABEL[section],
        content=content.strip(),
        evidence_references=evidence,
        review_status="pending",
    )


def items_exportable(*groups: list[AiDerivedItem]) -> bool:
    pending = [item for group in groups for item in group if item.review_status == "pending"]
    return not pending

from __future__ import annotations

import uuid

from app.models import AiDerivedItem, EvidenceReference, PlanTaskData, ProjectPlanData
from app.wsr.facts import _complete

AI_SECTIONS = (
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
)
STORED_AI_SECTIONS = ("client_needs",) + AI_SECTIONS

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


def items_from_situation_risks(
    plan: ProjectPlanData,
    risks: list[dict],
) -> list[AiDerivedItem]:
    """Turn current-plan risk-engine output into dashboard risk cards."""

    items: list[AiDerivedItem] = []
    for risk in risks:
        names = [str(name) for name in (risk.get("affectedTasks") or []) if name]
        evidence_lines = [str(line) for line in (risk.get("evidence") or []) if line]
        if not names:
            names = _names_mentioned(plan, evidence_lines)
        names = _incomplete_task_names(plan, names)
        if not names:
            continue
        title = str(risk.get("title") or "Project risk").strip()
        detail = evidence_lines[0] if evidence_lines else ""
        mitigation = str(risk.get("recommendedMitigation") or "").strip()
        parts = [part for part in (detail, f"Mitigation: {mitigation}" if mitigation else "") if part]
        content = f"{title}: {' '.join(parts)}" if parts else title
        item = resolve_item(plan, "risks", content, names)
        if item is not None:
            items.append(item)
    return items


def _incomplete_task_names(plan: ProjectPlanData, names: list[str]) -> list[str]:
    lookup = {task.name.lower(): task for task in plan.tasks if task.name}
    kept: list[str] = []
    for name in names:
        task = lookup.get(name.lower().strip())
        if task is None or task.is_summary or _complete(task):
            continue
        kept.append(task.name)
    return kept


def _names_mentioned(plan: ProjectPlanData, lines: list[str]) -> list[str]:
    haystack = " ".join(lines).lower()
    names: list[str] = []
    for task in plan.tasks:
        if task.is_summary or not task.name:
            continue
        if task.name.lower() in haystack:
            names.append(task.name)
    return names


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
        if task is None or task.is_summary or _complete(task):
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

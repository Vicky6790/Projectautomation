"""Project intelligence and consolidated risk engine for the executive summary."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.models import PlanTaskData, ProjectPlanData, WsrPlanFacts
from app.wsr.delay_engine import _driving_path_ids, _successor_map
from app.wsr.detection import client_owner_markers, go_live_markers, sign_off_markers, upcoming_horizon_days
from app.wsr.facts import (
    _candidate_date,
    _complete,
    _contains,
    _descendants,
    _due_date,
    _normalized_percent,
    _work_complete_percent,
    parse_date,
    reporting_windows,
    select_phase_summaries,
    task_labeler,
    work_based_progress,
)

_HEALTH_HYPHEN = {
    "on_track": "on-track",
    "at_risk": "at-risk",
    "off_track": "off-track",
    "unavailable": "unavailable",
}

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_executive_summary_input(
    plan: ProjectPlanData,
    facts: WsrPlanFacts,
    as_of: str,
) -> dict[str, Any]:
    as_of_d = date.fromisoformat(as_of)
    phases_rows = select_phase_summaries(
        plan.tasks,
        project_name=facts.project_name or plan.name,
        project_code=facts.project_code,
    )
    go_live_task = _go_live_task(plan.tasks, as_of_d)
    go_live_date = parse_date(facts.planned_go_live_date)
    progress = work_based_progress(plan.tasks)
    phase_payloads = [_phase_payload(plan.tasks, row, as_of_d) for row in phases_rows]
    milestones = _milestones(plan.tasks, as_of_d, go_live_task)
    dependencies = _dependencies(plan.tasks, as_of_d, go_live_task)
    risks = _risks(
        plan,
        as_of_d,
        phase_payloads,
        milestones,
        dependencies,
        go_live_task,
        go_live_date,
        progress,
        facts,
    )
    start = _earliest_start(plan.tasks)
    finish = _latest_finish(plan.tasks)
    return {
        "project": {
            "name": facts.project_name,
            "client": None,
            "startDate": None if start is None else start.isoformat(),
            "plannedFinishDate": None if finish is None else finish.isoformat(),
            "goLiveDate": facts.planned_go_live_date,
            "asOfDate": as_of,
            "phaseCount": facts.phase_count,
        },
        "progress": {
            "metric": progress["metric"],
            "overallPercent": progress["overall_percent"],
            "totalPlannedWorkHours": progress["planned"],
            "totalActualWorkHours": progress["actual"],
            "totalRemainingWorkHours": progress["remaining"],
        },
        "phases": phase_payloads,
        "milestones": milestones,
        "dependencies": dependencies,
        "risks": risks,
        "health": {
            "overall": _HEALTH_HYPHEN.get(facts.project_health, facts.project_health),
            "schedule": _schedule_health(plan.tasks, as_of_d),
            "progress": _progress_health(progress),
            "milestone": _milestone_health(milestones),
            "dependency": _dependency_health(dependencies),
            "goLive": _go_live_health(go_live_task, go_live_date, as_of_d),
            "resource": _resource_health(plan, progress, go_live_date, as_of_d, facts),
        },
        "delayMapping": _delay_mapping_snapshot(facts.delay_mapping),
    }


def _go_live_task(tasks: list[PlanTaskData], as_of: date) -> PlanTaskData | None:
    named = [
        task
        for task in tasks
        if _contains(task.gate, go_live_markers()) or _contains(task.name, go_live_markers())
    ]
    if not named:
        return None
    dated = [(task, when) for task in named if (when := _candidate_date(task)) is not None]
    if not dated:
        return named[0]
    future = [(task, when) for task, when in dated if when >= as_of]
    if future:
        return min(future, key=lambda item: item[1])[0]
    return max(dated, key=lambda item: item[1])[0]


def _phase_payload(tasks: list[PlanTaskData], phase: PlanTaskData, as_of: date) -> dict[str, Any]:
    children = _descendants(tasks, phase)
    leaves = [task for task in children if not task.is_summary]
    work = work_based_progress(leaves)
    return {
        "id": str(phase.id),
        "name": phase.name,
        "percentComplete": _work_complete_percent(phase),
        "plannedWorkHours": work["planned"],
        "actualWorkHours": work["actual"],
        "remainingWorkHours": work["remaining"],
        "startDate": phase.scheduled_start or _min_date(leaves, "scheduled_start"),
        "finishDate": phase.scheduled_finish or _max_date(leaves, "scheduled_finish"),
        "status": _phase_status(leaves, as_of, work),
    }


def _phase_status(
    leaves: list[PlanTaskData],
    as_of: date,
    work: dict[str, float | str | None],
) -> str:
    if not leaves:
        return "unavailable"
    overdue = [
        task
        for task in leaves
        if not _complete(task) and (_due_date(task) or _candidate_date(task) or date.max) < as_of
    ]
    if overdue:
        return "off-track" if len(overdue) >= max(1, len(leaves) // 2) else "at-risk"
    if work["metric"] == "unavailable" and not any(task.percent_complete or task.actual_start for task in leaves):
        dated = any(_candidate_date(task) for task in leaves)
        return "on-track" if dated else "unavailable"
    return "on-track"


def _milestones(
    tasks: list[PlanTaskData],
    as_of: date,
    go_live: PlanTaskData | None,
) -> dict[str, list[dict[str, Any]]]:
    _current_start, _current_end, upcoming_start, upcoming_end = reporting_windows(as_of)
    completed: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    for task in tasks:
        if not _is_milestone_like(task, go_live):
            continue
        planned = _candidate_date(task)
        if _complete(task):
            actual = parse_date(task.actual_finish) or planned
            if actual is None or actual > as_of:
                continue
            completed.append(
                {
                    "id": str(task.id),
                    "name": task.name,
                    "actualDate": None if actual is None else actual.isoformat(),
                    "evidence": _completion_evidence(task),
                }
            )
            continue
        if planned is None:
            continue
        if planned < as_of:
            overdue.append(
                {
                    "id": str(task.id),
                    "name": task.name,
                    "plannedDate": planned.isoformat(),
                    "daysOverdue": (as_of - planned).days,
                    "percentComplete": _normalized_percent(task.percent_complete),
                }
            )
        elif upcoming_start <= planned <= upcoming_end:
            upcoming.append(
                {
                    "id": str(task.id),
                    "name": task.name,
                    "plannedDate": planned.isoformat(),
                    "daysToMilestone": (planned - as_of).days,
                    "percentComplete": _normalized_percent(task.percent_complete),
                }
            )
    completed.sort(key=lambda item: item.get("actualDate") or "", reverse=True)
    upcoming.sort(key=lambda item: item.get("plannedDate") or "")
    overdue.sort(key=lambda item: item.get("daysOverdue") or 0, reverse=True)
    return {
        "completed": completed[:8],
        "upcoming": upcoming[:8],
        "overdue": overdue[:8],
    }


def _is_milestone_like(task: PlanTaskData, go_live: PlanTaskData | None) -> bool:
    if task.is_summary:
        return False
    if task.is_milestone or (task.gate or "").strip():
        return True
    if go_live is not None and task.id == go_live.id:
        return True
    return _contains(task.name, go_live_markers()) or _contains(task.name, sign_off_markers())


def _completion_evidence(task: PlanTaskData) -> str:
    parts: list[str] = []
    if task.actual_finish:
        parts.append(f"Actual finish {task.actual_finish[:10]}")
    if _normalized_percent(task.percent_complete) >= 99.5:
        parts.append("Percent complete 100")
    if (task.gate or "").strip():
        parts.append(f"Gate field: {task.gate.strip()}")
    if _contains(task.name, sign_off_markers()) or _contains(task.gate, sign_off_markers()):
        parts.append("Plan name/gate includes sign-off language")
    return "; ".join(parts) if parts else "Marked complete in the plan"


def _dependencies(
    tasks: list[PlanTaskData],
    as_of: date,
    go_live: PlanTaskData | None,
) -> list[dict[str, Any]]:
    by_id = {task.id: task for task in tasks}
    successors = _successor_map(tasks)
    go_live_id = None if go_live is None else go_live.id
    rows: list[dict[str, Any]] = []
    for task in tasks:
        if task.is_summary or not task.predecessor_ids or _complete(task):
            continue
        for pred_id in task.predecessor_ids:
            predecessor = by_id.get(pred_id)
            if predecessor is None or predecessor.is_summary or _complete(predecessor):
                continue
            delayed = _is_delayed(predecessor, as_of)
            if not delayed:
                continue
            on_path = _reaches(successors, predecessor.id, go_live_id)
            rows.append(
                {
                    "predecessorId": str(predecessor.id),
                    "predecessorName": predecessor.name,
                    "successorId": str(task.id),
                    "successorName": task.name,
                    "delayed": True,
                    "critical": _is_critical(predecessor) or _is_critical(task),
                    "goLiveImpact": on_path,
                }
            )
    return sorted(
        rows,
        key=lambda item: (
            not item["goLiveImpact"],
            not item["critical"],
            item["predecessorName"],
        ),
    )[:40]


def _is_delayed(task: PlanTaskData, as_of: date) -> bool:
    if _complete(task):
        return False
    due = _due_date(task) or _candidate_date(task)
    return due is not None and due < as_of


def _is_critical(task: PlanTaskData) -> bool:
    if task.critical is True:
        return True
    return task.total_slack_days is not None and task.total_slack_days <= 0


def _reaches(successors: dict[int, list[int]], start: int, target: int | None) -> bool:
    if target is None:
        return False
    if start == target:
        return True
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for nxt in successors.get(current, []):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _has_recorded_progress(task: PlanTaskData) -> bool:
    if parse_date(task.actual_start) is not None:
        return True
    return _normalized_percent(task.percent_complete) > 0


def _started_by(task: PlanTaskData, as_of: date) -> bool:
    if _has_recorded_progress(task):
        return True
    start = parse_date(task.scheduled_start)
    if start is not None:
        return start <= as_of
    finish = parse_date(task.scheduled_finish)
    return finish is not None and finish <= as_of


def _phase_is_complete(phase: PlanTaskData, children: list[PlanTaskData]) -> bool:
    if _complete(phase):
        return True
    pct = _work_complete_percent(phase)
    if pct is not None and pct >= 99.5:
        return True
    if children and all(_complete(child) for child in children):
        return True
    return _normalized_percent(phase.percent_complete) >= 99.5


def _phase_leaf_children(tasks: list[PlanTaskData], phase: PlanTaskData) -> list[PlanTaskData]:
    return [child for child in _descendants(tasks, phase) if not child.is_summary]


def _phase_start(phase: PlanTaskData, children: list[PlanTaskData]) -> date | None:
    start = parse_date(phase.scheduled_start) or parse_date(phase.actual_start)
    if start is not None:
        return start
    starts = [
        parse_date(child.scheduled_start) or parse_date(child.actual_start)
        for child in children
    ]
    starts = [day for day in starts if day is not None]
    return min(starts) if starts else None


def _is_unstarted_go_live_row(
    phase: PlanTaskData, children: list[PlanTaskData], as_of: date
) -> bool:
    if not _contains(phase.name, go_live_markers()):
        return False
    if _has_recorded_progress(phase) or any(_has_recorded_progress(child) for child in children):
        return False
    start = _phase_start(phase, children)
    finish = parse_date(phase.scheduled_finish)
    if start is not None:
        return start > as_of
    return finish is None or finish > as_of


def _active_phase_rows(
    tasks: list[PlanTaskData],
    as_of: date,
    phase_rows: list[PlanTaskData],
) -> list[PlanTaskData]:
    incomplete: list[tuple[PlanTaskData, list[PlanTaskData]]] = []
    for phase in phase_rows:
        children = _phase_leaf_children(tasks, phase)
        if _phase_is_complete(phase, children):
            continue
        if _is_unstarted_go_live_row(phase, children, as_of):
            continue
        incomplete.append((phase, children))

    active: list[PlanTaskData] = []
    for phase, children in incomplete:
        has_progress = _has_recorded_progress(phase) or any(
            _has_recorded_progress(child) for child in children
        )
        if not has_progress:
            continue
        start = _phase_start(phase, children)
        if start is not None and start > as_of:
            continue
        active.append(phase)
    if active:
        return active

    for phase, children in incomplete:
        start = _phase_start(phase, children)
        if start is not None and start > as_of:
            continue
        return [phase]
    return []


def _task_ids_for_phases(
    tasks: list[PlanTaskData], phases: list[PlanTaskData]
) -> set[int]:
    ids: set[int] = set()
    for phase in phases:
        ids.add(phase.id)
        ids.update(child.id for child in _descendants(tasks, phase))
    return ids


def _in_current_scope(task: PlanTaskData, ctx: dict[str, Any]) -> bool:
    as_of: date = ctx["as_of"]
    active_ids: set[int] = ctx.get("active_task_ids") or set()
    if active_ids:
        return task.id in active_ids
    delivery_phases = [
        phase
        for phase in (ctx.get("phase_rows") or [])
        if not _contains(phase.name, go_live_markers())
    ]
    if delivery_phases:
        return False
    start = parse_date(task.scheduled_start)
    if start is not None and start > as_of and not _has_recorded_progress(task):
        return False
    return _started_by(task, as_of) or _is_overdue(task, as_of)


def _next_dependent_phase_name(ctx: dict[str, Any]) -> str | None:
    active = ctx.get("active_phases") or []
    all_phases = ctx.get("phase_rows") or []
    if not active or not all_phases:
        return None
    active_ids = {phase.id for phase in active}
    later = [phase for phase in all_phases if phase.id not in active_ids]
    if not later:
        return None
    successors = ctx["successors"]
    active_tasks: set[int] = ctx.get("active_task_ids") or set()
    for phase in later:
        child_ids = {phase.id, *[child.id for child in _descendants(ctx["tasks"], phase)]}
        for src in active_tasks:
            if any(dest in child_ids for dest in successors.get(src, [])):
                return phase.name
    return None


def _focus_area_lines(ctx: dict[str, Any], leaves: list[PlanTaskData], mapping_by_name) -> list[str]:
    active = ctx.get("active_phases") or []
    as_of: date = ctx["as_of"]
    if not active:
        return []
    phase_name = active[0].name if len(active) == 1 else " and ".join(phase.name for phase in active)
    active_ids: set[int] = ctx.get("active_task_ids") or set()
    scoped = [task for task in leaves if task.id in active_ids and not _complete(task)]
    lines: list[str] = []
    if any(
        task.is_milestone or _contains(task.name, sign_off_markers()) for task in scoped
    ):
        lines.append(f"Close pending {phase_name} reviews/sign-offs")
    if any(_is_overdue(task, as_of) for task in scoped):
        lines.append(f"Resolve delayed {phase_name} activities")
    lines.append(f"Complete current {phase_name} deliverables")
    if any(_is_client_task(task, mapping_by_name.get(task.name)) for task in scoped):
        lines.append("Clear client dependencies")
    nxt = _next_dependent_phase_name(ctx)
    if nxt:
        lines.append(f"Protect the next directly dependent {nxt} activities")
    return lines[:5]


def _risks(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[dict[str, Any]],
    milestones: dict[str, list[dict[str, Any]]],
    dependencies: list[dict[str, Any]],
    go_live: PlanTaskData | None,
    go_live_date: date | None,
    progress: dict[str, float | str | None],
    facts: WsrPlanFacts,
) -> list[dict[str, Any]]:
    by_id = {task.id: task for task in plan.tasks}
    leaves = [task for task in plan.tasks if not task.is_summary]
    successors = _successor_map(plan.tasks)
    driving_ids = _driving_path_ids(go_live, plan.tasks, successors) if go_live else set()
    milestone_ids = {task.id for task in leaves if _is_milestone_like(task, go_live)}
    mapping_by_name = _mapping_rows_by_name(facts)
    mapping = facts.delay_mapping
    label = task_labeler(
        plan.tasks,
        project_name=facts.project_name or plan.name,
        project_code=facts.project_code,
    )
    ctx = {
        "successors": successors,
        "driving_ids": driving_ids,
        "go_live": go_live,
        "milestone_ids": milestone_ids,
        "phases": phases,
        "tasks": plan.tasks,
        "by_id": by_id,
        "as_of": as_of,
    }
    phase_rows = select_phase_summaries(
        plan.tasks,
        project_name=facts.project_name or plan.name,
        project_code=facts.project_code,
    )
    active_phases = _active_phase_rows(plan.tasks, as_of, phase_rows)
    ctx["phase_rows"] = phase_rows
    ctx["active_phases"] = active_phases
    ctx["active_task_ids"] = _task_ids_for_phases(plan.tasks, active_phases)
    risks: list[dict[str, Any]] = []
    seen_tasks: set[int] = set()

    for task in sorted(
        (item for item in leaves if _is_overdue(item, as_of) and _in_current_scope(item, ctx)),
        key=lambda item: (_due_date(item) or date.min, item.name),
    ):
        row = mapping_by_name.get(task.name)
        classified = _classify_impact(task, row, ctx)
        if classified is None:
            continue
        category, severity = classified
        seen_tasks.add(task.id)
        risks.append(
            _risk_record(
                key=f"overdue:{task.id}",
                task=task,
                category=category,
                severity=severity,
                label=label,
                as_of=as_of,
                mapping_row=row,
                ctx=ctx,
            )
        )

    for dep in dependencies:
        pred = by_id.get(int(dep["predecessorId"]))
        succ = by_id.get(int(dep["successorId"]))
        if pred is None or succ is None or _complete(pred) or _complete(succ):
            continue
        if pred.id in seen_tasks:
            continue
        if not _in_current_scope(pred, ctx):
            continue
        classified = _classify_impact(pred, mapping_by_name.get(pred.name), ctx)
        if classified is None:
            continue
        category, severity = classified
        seen_tasks.add(pred.id)
        record = _risk_record(
            key=f"dep:{pred.id}:{succ.id}",
            task=pred,
            category=category,
            severity=severity,
            label=label,
            as_of=as_of,
            mapping_row=mapping_by_name.get(pred.name),
            ctx=ctx,
        )
        record["evidence"] = [
            f"{label(pred)} is incomplete with finish before {as_of.isoformat()}; "
            f"{label(succ)} depends on it"
        ]
        record["affectedTasks"] = [pred.name, succ.name]
        record["projectImpact"] = _impact_sentence(
            category, [succ], go_live, _affected_phase(pred, phases, plan.tasks), label
        )
        record["recommendedMitigation"] = _mitigation_text(
            label(pred),
            [label(succ)],
            pred,
            _is_client_task(pred, mapping_by_name.get(pred.name)),
        )
        risks.append(record)

    for item in milestones.get("overdue") or []:
        task = by_id.get(int(item["id"]))
        if task is None or _complete(task) or task.id in seen_tasks:
            continue
        if not _in_current_scope(task, ctx):
            continue
        classified = _classify_impact(task, mapping_by_name.get(task.name), ctx)
        if classified is None:
            continue
        category, severity = classified
        seen_tasks.add(task.id)
        record = _risk_record(
            key=f"milestone-overdue:{task.id}",
            task=task,
            category=category,
            severity=severity,
            label=label,
            as_of=as_of,
            mapping_row=mapping_by_name.get(task.name),
            ctx=ctx,
        )
        record["evidence"] = [
            f"{label(task)} was due on {item.get('plannedDate')} "
            f"and is {int(item.get('percentComplete') or 0)}% complete"
        ]
        risks.append(record)

    for item in milestones.get("upcoming") or []:
        task = by_id.get(int(item["id"]))
        if task is None or _complete(task) or task.id in seen_tasks:
            continue
        if not _in_current_scope(task, ctx):
            continue
        pct = float(item.get("percentComplete") or 0)
        days = item.get("daysToMilestone")
        if pct >= 50:
            continue
        if not isinstance(days, int) or days > upcoming_horizon_days():
            continue
        slack = task.total_slack_days
        if slack is not None and slack > days:
            continue
        classified = _classify_impact(task, mapping_by_name.get(task.name), ctx)
        if classified is None:
            continue
        category, severity = classified
        seen_tasks.add(task.id)
        record = _risk_record(
            key=f"upcoming:{task.id}",
            task=task,
            category=category,
            severity=severity,
            label=label,
            as_of=as_of,
            mapping_row=mapping_by_name.get(task.name),
            ctx=ctx,
        )
        record["evidence"] = [
            f"{label(task)} is due in {days} day(s) and is {int(pct)}% complete"
        ]
        record["targetDate"] = item.get("plannedDate") or record.get("targetDate")
        risks.append(record)

    if mapping is not None:
        by_name = {task.name: task for task in leaves if task.name}
        for row in mapping.rows:
            if row.task_type not in {"delay", "additional", "new_task"}:
                continue
            if not row.go_live_path_impact and not (row.go_live_impact_days or 0) > 0:
                continue
            task = by_name.get(row.name)
            if task is None or _complete(task) or task.id in seen_tasks:
                continue
            if not _in_current_scope(task, ctx):
                continue
            classified = _classify_impact(task, row, ctx)
            if classified is None:
                continue
            category, severity = classified
            seen_tasks.add(task.id)
            record = _risk_record(
                key=f"mapping:{task.id}",
                task=task,
                category=category,
                severity=severity,
                label=label,
                as_of=as_of,
                mapping_row=row,
                ctx=ctx,
            )
            shift_days = row.shift_days if row.shift_days is not None else row.go_live_impact_days
            if isinstance(shift_days, int) and shift_days > 0:
                record["evidence"] = [
                    f"{label(task)} is a {row.task_type} item with a {shift_days}-day Go-Live path movement"
                ]
            risks.append(record)

    focus_lines = _focus_area_lines(ctx, leaves, mapping_by_name)
    by_name = {task.name: task for task in leaves}

    def _rank(row: dict[str, Any]) -> tuple:
        names = [str(name) for name in (row.get("affectedTasks") or [])]
        active_ids = ctx.get("active_task_ids") or set()
        in_phase = False
        for name in names:
            hit = by_name.get(name)
            if hit is not None and hit.id in active_ids:
                in_phase = True
                break
        return (
            0 if in_phase or not active_ids else 1,
            _SEVERITY_RANK.get(str(row.get("severity")), 9),
            0 if row.get("goLiveImpact") else 1,
            row.get("title") or "",
        )

    risks.sort(key=_rank)
    selected = risks[:5]
    focus_task = next(
        (task for task in leaves if _in_current_scope(task, ctx) and not _complete(task)),
        None,
    )
    if focus_lines and focus_task is not None and selected:
        selected = [
            {
                "id": "focus-areas",
                "title": "Focus Areas",
                "category": "Focus Areas",
                "kind": "focus",
                "severity": "low",
                "evidence": focus_lines,
                "affectedTasks": [focus_task.name],
                "goLiveImpact": False,
                "projectImpact": "",
                "recommendedMitigation": "",
                "owner": None,
                "targetDate": None,
            },
            *selected,
        ]
    return selected


def _is_overdue(task: PlanTaskData, as_of: date) -> bool:
    if _complete(task):
        return False
    finish = _due_date(task)
    return finish is not None and finish < as_of


def _matters_for_risk(
    task: PlanTaskData,
    driving_ids: set[int],
    go_live: PlanTaskData | None,
    all_tasks: list[PlanTaskData],
) -> bool:
    ctx = {
        "successors": _successor_map(all_tasks),
        "driving_ids": driving_ids,
        "go_live": go_live,
        "milestone_ids": {
            item.id
            for item in all_tasks
            if not item.is_summary and _is_milestone_like(item, go_live)
        },
        "phases": [],
        "tasks": all_tasks,
        "by_id": {item.id: item for item in all_tasks},
        "as_of": date.min,
    }
    return _classify_impact(task, None, ctx) is not None


def _overdue_line(task_path: str, task: PlanTaskData, as_of: date, days: int | None) -> str:
    finish = (_due_date(task) or _candidate_date(task) or as_of).isoformat()
    pct = int(_normalized_percent(task.percent_complete))
    suffix = f" ({days} day(s) overdue)" if days is not None and days > 0 else ""
    return f"{task_path} is {pct}% complete with finish {finish}{suffix}"


def _mitigate_overdue(task_path: str, successor_paths: list[str]) -> str:
    if successor_paths:
        joined = ", ".join(successor_paths[:2])
        return f"Complete {task_path} or re-baseline finish before {joined} can proceed."
    return f"Complete {task_path} or update its finish date in the plan."


def _mapping_rows_by_name(facts: WsrPlanFacts) -> dict[str, Any]:
    mapping = facts.delay_mapping
    if mapping is None:
        return {}
    return {row.name: row for row in mapping.rows if row.name}


def _task_owner(task: PlanTaskData, mapping_row: Any) -> str | None:
    for item in task.assignments:
        if item.resource_name:
            return item.resource_name
    if mapping_row is not None and getattr(mapping_row, "owner", None):
        return mapping_row.owner
    return None


def _is_client_task(task: PlanTaskData, mapping_row: Any) -> bool:
    if mapping_row is not None and getattr(mapping_row, "owner_class", None) == "client":
        return True
    markers = client_owner_markers()
    if not markers:
        return False
    names = [item.resource_name for item in task.assignments if item.resource_name]
    return any(any(marker in name.lower() for marker in markers) for name in names)


def _downstream_flags(task: PlanTaskData, ctx: dict[str, Any]) -> tuple[bool, bool, bool]:
    successors: dict[int, list[int]] = ctx["successors"]
    go_live: PlanTaskData | None = ctx["go_live"]
    go_live_id = None if go_live is None else go_live.id
    milestone_ids: set[int] = ctx["milestone_ids"]
    found_gl = task.id in ctx["driving_ids"] or (go_live_id is not None and task.id == go_live_id)
    found_ms = task.id in milestone_ids
    found_phase = False
    seen = {task.id}
    queue = list(successors.get(task.id, []))
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        if go_live_id is not None and nid == go_live_id:
            found_gl = True
        if nid in milestone_ids:
            found_ms = True
        for nxt in successors.get(nid, []):
            if nxt not in seen:
                queue.append(nxt)
    phase_name = _affected_phase(task, ctx["phases"], ctx["tasks"])
    due = _due_date(task)
    if phase_name and due is not None:
        phase = next(
            (item for item in ctx["phases"] if item.get("name") == phase_name),
            None,
        )
        phase_finish = parse_date(None if phase is None else phase.get("finishDate"))
        if phase_finish is not None and due == phase_finish and _is_overdue(task, ctx["as_of"]):
            found_phase = True
    return found_gl, found_ms, found_phase


def _classify_impact(task: PlanTaskData, mapping_row: Any, ctx: dict[str, Any]) -> tuple[str, str] | None:
    if _complete(task):
        return None
    found_gl, found_ms, found_phase = _downstream_flags(task, ctx)
    mapping_gl = bool(
        mapping_row is not None
        and (
            getattr(mapping_row, "go_live_path_impact", False)
            or (getattr(mapping_row, "go_live_impact_days", None) or 0) > 0
        )
    )
    additional = mapping_row is not None and getattr(mapping_row, "task_type", None) in {
        "additional",
        "new_task",
    }
    slack = task.total_slack_days
    has_float = slack is not None and slack > 0
    succs = _linked_successors(task, ctx)
    has_succ = bool(succs)
    material = found_gl or found_ms or found_phase or mapping_gl or has_succ
    if additional:
        material = mapping_gl or found_gl or found_ms
    if not material:
        return None
    if has_float and not (found_gl or found_ms or found_phase or mapping_gl or has_succ):
        return None
    go_live: PlanTaskData | None = ctx.get("go_live")
    hits_go_live = go_live is not None and (
        task.id == go_live.id or any(item.id == go_live.id for item in succs)
    )
    nxt = _successor_phase_name(task, ctx)
    if hits_go_live or mapping_gl:
        return "Project/Go-Live Impact", "high"
    if nxt:
        return "Downstream Phase Impact", "high" if found_gl else "medium"
    if found_ms or task.is_milestone:
        return "Milestone Impact", "high" if found_gl else "medium"
    if found_gl:
        return "Project/Go-Live Impact", "high"
    return "Current Phase Impact", "medium"


def _successor_phase_name(task: PlanTaskData, ctx: dict[str, Any]) -> str | None:
    active_ids: set[int] = ctx.get("active_task_ids") or set()
    tasks: list[PlanTaskData] = ctx["tasks"]
    phase_rows = ctx.get("phase_rows") or []
    for succ in _linked_successors(task, ctx):
        if succ.id in active_ids:
            continue
        for phase in phase_rows:
            children = {phase.id, *[child.id for child in _descendants(tasks, phase)]}
            if succ.id in children:
                return phase.name
    return None


def _impact_sentence(
    category: str,
    successors: list[PlanTaskData],
    go_live: PlanTaskData | None,
    phase_name: str | None,
    label,
) -> str:
    succ = label(successors[0]) if successors else None
    if category == "Project/Go-Live Impact":
        if succ:
            return f"Delayed current-phase work can hold back {succ} and put Go-Live under schedule pressure."
        return "Delayed current-phase work can put Go-Live under schedule pressure."
    if category == "Milestone Impact":
        if succ:
            return f"This can shift successor dates and put {succ} under schedule pressure."
        return "This can put a current-phase milestone finish under schedule pressure."
    if category == "Downstream Phase Impact":
        if succ:
            return f"This is blocking dependent {succ} activities."
        if phase_name:
            return f"This can hold the next dependent {phase_name} work."
        return "This can hold the next directly dependent phase."
    if category == "Current Phase Impact" and phase_name:
        return f"This can hold the {phase_name} phase finish."
    if go_live is not None:
        return "This can affect current-phase completion and the project schedule."
    return "This can affect completion of the current phase."


def _mitigation_text(
    task_path: str,
    successor_paths: list[str],
    task: PlanTaskData,
    client: bool,
) -> str:
    target = (task.scheduled_finish or "")[:10] or None
    protect = successor_paths[0] if successor_paths else "the current schedule"
    if client and target:
        return f"Prioritise client review and complete {task_path} by {target} to protect {protect}."
    if client:
        return f"Prioritise client review and complete {task_path} to protect {protect}."
    if target and successor_paths:
        return f"Complete {task_path} by {target} to protect {protect}."
    if target:
        return f"Complete {task_path} by {target} to protect the current schedule."
    return _mitigate_overdue(task_path, successor_paths)


def _risk_record(
    *,
    key: str,
    task: PlanTaskData,
    category: str,
    severity: str,
    label,
    as_of: date,
    mapping_row: Any,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    finish = _due_date(task) or _candidate_date(task)
    days = (as_of - finish).days if finish and finish < as_of else None
    succ_tasks = _linked_successors(task, ctx)
    on_path = task.id in ctx["driving_ids"] or _tasks_affect_go_live(
        [task], ctx["go_live"], ctx["tasks"]
    )
    owner = _task_owner(task, mapping_row)
    shift = None
    if mapping_row is not None:
        shift = mapping_row.shift_days if mapping_row.shift_days is not None else mapping_row.go_live_impact_days
    evidence = [_overdue_line(label(task), task, as_of, days)]
    if isinstance(shift, int) and shift > 0:
        evidence.append(f"Delay Mapping shows a {shift}-day movement versus baseline")
    return {
        "id": key,
        "title": category,
        "category": category,
        "severity": severity,
        "evidence": evidence,
        "affectedTasks": [task.name, *[item.name for item in succ_tasks[:2]]],
        "goLiveImpact": on_path,
        "projectImpact": _impact_sentence(
            category,
            succ_tasks,
            ctx["go_live"],
            _affected_phase(task, ctx["phases"], ctx["tasks"]),
            label,
        ),
        "recommendedMitigation": _mitigation_text(
            label(task),
            [label(item) for item in succ_tasks],
            task,
            _is_client_task(task, mapping_row),
        ),
        "owner": owner or "Not specified",
        "targetDate": task.scheduled_finish or "Not specified",
    }


def _linked_successors(task: PlanTaskData, ctx: dict[str, Any]) -> list[PlanTaskData]:
    by_id: dict[int, PlanTaskData] = ctx["by_id"]
    found: list[PlanTaskData] = []
    for succ_id in ctx["successors"].get(task.id, []):
        succ = by_id.get(succ_id)
        if succ is None or succ.is_summary or _complete(succ):
            continue
        found.append(succ)
    return found


def _direct_successors(task: PlanTaskData, tasks: list[PlanTaskData]) -> list[PlanTaskData]:
    by_id = {item.id: item for item in tasks}
    found: list[PlanTaskData] = []
    for succ_id in task.successor_ids:
        succ = by_id.get(succ_id)
        if succ is None or succ.is_summary or _complete(succ):
            continue
        found.append(succ)
    return found


def _incomplete_critical_tasks(leaves: list[PlanTaskData], driving_ids: set[int]) -> list[PlanTaskData]:
    return [
        task
        for task in leaves
        if not _complete(task) and (task.id in driving_ids or _is_critical(task))
    ]


def _affected_phase(
    task: PlanTaskData,
    phases: list[dict[str, Any]],
    tasks: list[PlanTaskData],
) -> str | None:
    for phase in phases:
        parent = next((item for item in tasks if str(item.id) == phase["id"]), None)
        if parent is None:
            continue
        if any(child.id == task.id for child in _descendants(tasks, parent)):
            return phase["name"]
    return None


def _tasks_affect_go_live(
    tasks: list[PlanTaskData],
    go_live: PlanTaskData | None,
    all_tasks: list[PlanTaskData],
) -> bool:
    if go_live is None:
        return False
    successors: dict[int, list[int]] = defaultdict(list)
    for task in all_tasks:
        for pred in task.predecessor_ids:
            successors[pred].append(task.id)
    return any(_reaches(successors, task.id, go_live.id) for task in tasks)


def _earliest_start(tasks: list[PlanTaskData]) -> date | None:
    dates = [parse_date(task.scheduled_start) for task in tasks]
    ok = [item for item in dates if item]
    return min(ok) if ok else None


def _latest_finish(tasks: list[PlanTaskData]) -> date | None:
    dates = [parse_date(task.scheduled_finish) for task in tasks]
    ok = [item for item in dates if item]
    return max(ok) if ok else None


def _min_date(tasks: list[PlanTaskData], field: str) -> str | None:
    dates = [parse_date(getattr(task, field)) for task in tasks]
    ok = [item for item in dates if item]
    return None if not ok else min(ok).isoformat()


def _max_date(tasks: list[PlanTaskData], field: str) -> str | None:
    dates = [parse_date(getattr(task, field)) for task in tasks]
    ok = [item for item in dates if item]
    return None if not ok else max(ok).isoformat()


def _schedule_health(tasks: list[PlanTaskData], as_of: date) -> str:
    leaves = [task for task in tasks if not task.is_summary]
    overdue = any(_is_overdue(task, as_of) for task in leaves)
    dated = any(_due_date(task) for task in leaves)
    if not dated:
        return "unavailable"
    return "at-risk" if overdue else "on-track"


def _progress_health(progress: dict[str, float | str | None]) -> str:
    if progress["metric"] != "work" or progress["overall_percent"] is None:
        return "unavailable"
    percent = float(progress["overall_percent"])
    if percent < 10:
        return "at-risk"
    return "on-track"


def _milestone_health(milestones: dict[str, list[dict[str, Any]]]) -> str:
    if milestones.get("overdue"):
        return "off-track"
    if milestones.get("upcoming") or milestones.get("completed"):
        return "on-track"
    return "unavailable"


def _dependency_health(dependencies: list[dict[str, Any]]) -> str:
    if not dependencies:
        return "unavailable"
    if any(item["delayed"] for item in dependencies):
        return "at-risk"
    return "on-track"


def _go_live_health(
    go_live: PlanTaskData | None,
    go_live_date: date | None,
    as_of: date,
) -> str:
    if go_live is None or go_live_date is None:
        return "unavailable"
    if go_live_date > as_of:
        return "upcoming"
    if go_live_date == as_of:
        return "today"
    if not _complete(go_live):
        return "overdue"
    return "on-track"


def _resource_health(
    plan: ProjectPlanData,
    progress: dict[str, float | str | None],
    go_live_date: date | None,
    as_of: date,
    facts: WsrPlanFacts,
) -> str:
    if progress["metric"] != "work":
        return "unavailable"
    remaining = progress["remaining"]
    people = facts.people_planned or facts.resources_deployed
    if remaining is None or people is None or people <= 0:
        return "unavailable"
    if go_live_date is None:
        return "unavailable"
    days = max((go_live_date - as_of).days, 0)
    capacity_hours = people * 8 * max(days, 1)
    if float(remaining) > capacity_hours:
        return "off-track"
    if float(remaining) > capacity_hours * 0.7:
        return "at-risk"
    return "on-track"


def _delay_mapping_snapshot(mapping) -> dict[str, Any] | None:
    if mapping is None:
        return None
    return {
        "baselineGoLive": mapping.baseline_go_live,
        "currentGoLive": mapping.current_go_live,
        "grossWorkingDayShift": mapping.gross_working_day_shift,
        "holidays": mapping.holidays,
        "netWorkingDayShift": mapping.net_working_day_shift,
        "actualShiftWorkingDays": mapping.actual_shift_working_days,
        "delayedTaskCount": mapping.delayed_task_count,
        "totalCount": mapping.total_delayed_days,
        "reconciliationStatus": mapping.reconciliation_status,
        "reconciliationWarning": mapping.reconciliation_warning,
        "rows": [
            {
                "phase": row.parent_name,
                "task": row.name,
                "taskType": row.task_type,
                "owner": row.owner,
                "ownerClass": row.owner_class,
                "shiftDays": row.shift_days,
                "goLiveImpactDays": row.go_live_impact_days,
            }
            for row in mapping.rows
        ],
    }

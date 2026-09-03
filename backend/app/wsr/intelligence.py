"""Project intelligence and consolidated risk engine for the executive summary."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.models import PlanTaskData, ProjectPlanData, WsrPlanFacts
from app.wsr.delay_engine import _driving_path_ids, _successor_map
from app.wsr.detection import go_live_markers, sign_off_markers, upcoming_horizon_days
from app.wsr.facts import (
    _candidate_date,
    _complete,
    _contains,
    _descendants,
    _due_date,
    _normalized_percent,
    parse_date,
    select_phase_summaries,
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
        "percentComplete": work["overall_percent"],
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
    horizon = as_of + timedelta(days=upcoming_horizon_days())
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
        elif planned <= horizon:
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
    _ = phases
    by_id = {task.id: task for task in plan.tasks}
    leaves = [task for task in plan.tasks if not task.is_summary]
    successors = _successor_map(plan.tasks)
    driving_ids = _driving_path_ids(go_live, plan.tasks, successors) if go_live else set()
    risks: list[dict[str, Any]] = []
    seen: set[str] = set()

    for task in sorted(
        (item for item in leaves if _is_overdue(item, as_of)),
        key=lambda item: (_due_date(item) or date.min, item.name),
    ):
        if not _matters_for_risk(task, driving_ids, go_live, plan.tasks):
            continue
        key = f"overdue:{task.id}"
        if key in seen:
            continue
        seen.add(key)
        finish = _due_date(task) or _candidate_date(task)
        days = (as_of - finish).days if finish else None
        succ_names = _direct_successor_names(task, plan.tasks)
        on_path = task.id in driving_ids
        risks.append(
            {
                "id": key,
                "title": "Overdue work",
                "severity": "critical" if on_path and days and days > 7 else ("high" if on_path else "medium"),
                "evidence": [_overdue_line(task, as_of, days)],
                "affectedTasks": [task.name, *succ_names[:2]],
                "goLiveImpact": on_path or _tasks_affect_go_live([task], go_live, plan.tasks),
                "recommendedMitigation": _mitigate_overdue(task, succ_names),
            }
        )

    for dep in dependencies:
        pred = by_id.get(int(dep["predecessorId"]))
        succ = by_id.get(int(dep["successorId"]))
        if pred is None or succ is None or _complete(pred) or _complete(succ):
            continue
        if not dep.get("goLiveImpact") and not dep.get("critical"):
            continue
        key = f"dep:{pred.id}:{succ.id}"
        if key in seen:
            continue
        seen.add(key)
        risks.append(
            {
                "id": key,
                "title": "Critical dependency blocked",
                "severity": "critical" if dep.get("goLiveImpact") else "high",
                "evidence": [
                    f"{pred.name} is incomplete with finish before {as_of.isoformat()}; "
                    f"{succ.name} depends on it"
                ],
                "affectedTasks": [pred.name, succ.name],
                "goLiveImpact": bool(dep.get("goLiveImpact")),
                "recommendedMitigation": (
                    f"Complete {pred.name} to unblock {succ.name} on the schedule."
                ),
            }
        )

    for item in milestones.get("upcoming") or []:
        task = by_id.get(int(item["id"]))
        if task is None or _complete(task):
            continue
        pct = float(item.get("percentComplete") or 0)
        if pct >= 50:
            continue
        if not _matters_for_risk(task, driving_ids, go_live, plan.tasks):
            continue
        key = f"upcoming:{task.id}"
        if key in seen:
            continue
        seen.add(key)
        risks.append(
            {
                "id": key,
                "title": "Upcoming milestone at risk",
                "severity": "high" if task.id in driving_ids else "medium",
                "evidence": [
                    f"{task.name} is due in {item.get('daysToMilestone')} day(s) "
                    f"and is {int(pct)}% complete"
                ],
                "affectedTasks": [task.name],
                "goLiveImpact": go_live is not None and str(task.id) == str(go_live.id),
                "recommendedMitigation": (
                    f"Advance {task.name} to completion before {item.get('plannedDate')}."
                ),
            }
        )

    for item in milestones.get("overdue") or []:
        task = by_id.get(int(item["id"]))
        if task is None or _complete(task):
            continue
        if not _matters_for_risk(task, driving_ids, go_live, plan.tasks):
            continue
        key = f"milestone-overdue:{task.id}"
        if key in seen:
            continue
        seen.add(key)
        risks.append(
            {
                "id": key,
                "title": "Overdue milestone",
                "severity": "critical" if task.id in driving_ids else "high",
                "evidence": [
                    f"{task.name} was due on {item.get('plannedDate')} "
                    f"and is {int(item.get('percentComplete') or 0)}% complete"
                ],
                "affectedTasks": [task.name],
                "goLiveImpact": task.id in driving_ids,
                "recommendedMitigation": f"Close {task.name} or re-baseline its finish date.",
            }
        )

    if go_live is not None and go_live_date is not None and not _complete(go_live):
        shift = None
        mapping = facts.delay_mapping
        if mapping is not None:
            shift = mapping.actual_shift_working_days or mapping.net_working_day_shift
        if go_live_date < as_of or (isinstance(shift, int) and shift > 0):
            key = f"go-live:{go_live.id}"
            if key not in seen:
                seen.add(key)
                evidence = [f"{go_live.name} is planned on {go_live_date.isoformat()}"]
                if go_live_date < as_of:
                    evidence.append(
                        f"{go_live.name} is incomplete and finish is before the as-of date"
                    )
                if isinstance(shift, int) and shift > 0:
                    evidence.append(f"Delay Mapping shows a {shift}-day Go-Live shift")
                risks.append(
                    {
                        "id": key,
                        "title": "Go-Live impact",
                        "severity": "critical" if go_live_date < as_of else "high",
                        "evidence": evidence,
                        "affectedTasks": [go_live.name],
                        "goLiveImpact": True,
                        "recommendedMitigation": (
                            "Recover delayed predecessors on the Go-Live path before accepting the current date."
                        ),
                    }
                )

    resource = _resource_health(plan, progress, go_live_date, as_of, facts)
    if resource in {"at-risk", "off-track"} and progress["metric"] == "work":
        remaining = progress["remaining"]
        people = facts.people_planned or facts.resources_deployed
        if isinstance(remaining, (int, float)) and remaining > 0 and people and go_live_date:
            key = "resource-pressure"
            if key not in seen:
                seen.add(key)
                days = max((go_live_date - as_of).days, 0)
                risks.append(
                    {
                        "id": key,
                        "title": "Remaining effort pressure",
                        "severity": "high" if resource == "off-track" else "medium",
                        "evidence": [
                            f"Remaining work is {remaining:g} hours across incomplete leaf tasks",
                            f"Named resources in plan: {people}; calendar days to Go-Live: {days}",
                        ],
                        "affectedTasks": _incomplete_critical_names(leaves, driving_ids)[:4],
                        "goLiveImpact": True,
                        "recommendedMitigation": (
                            "Reconcile remaining work hours with named capacity before Go-Live."
                        ),
                    }
                )

    risks.sort(
        key=lambda row: (
            _SEVERITY_RANK.get(str(row.get("severity")), 9),
            0 if row.get("goLiveImpact") else 1,
            row.get("title") or "",
        )
    )
    return risks[:12]


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
    if _complete(task):
        return False
    if task.id in driving_ids:
        return True
    if _is_critical(task):
        return True
    return go_live is not None and _tasks_affect_go_live([task], go_live, all_tasks)


def _overdue_line(task: PlanTaskData, as_of: date, days: int | None) -> str:
    finish = (_due_date(task) or _candidate_date(task) or as_of).isoformat()
    pct = int(_normalized_percent(task.percent_complete))
    suffix = f" ({days} day(s) overdue)" if days is not None and days > 0 else ""
    return f"{task.name} is {pct}% complete with finish {finish}{suffix}"


def _mitigate_overdue(task: PlanTaskData, successor_names: list[str]) -> str:
    if successor_names:
        joined = ", ".join(successor_names[:2])
        return f"Complete {task.name} or re-baseline finish before {joined} can proceed."
    return f"Complete {task.name} or update its finish date in the plan."


def _direct_successor_names(task: PlanTaskData, tasks: list[PlanTaskData]) -> list[str]:
    by_id = {item.id: item for item in tasks}
    names: list[str] = []
    for succ_id in task.successor_ids:
        succ = by_id.get(succ_id)
        if succ is None or succ.is_summary or _complete(succ):
            continue
        names.append(succ.name)
    return names


def _incomplete_critical_names(leaves: list[PlanTaskData], driving_ids: set[int]) -> list[str]:
    names: list[str] = []
    for task in leaves:
        if _complete(task):
            continue
        if task.id in driving_ids or _is_critical(task):
            names.append(task.name)
    return names


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
        "totalCount": mapping.total_delayed_days,
        "reconciliationStatus": mapping.reconciliation_status,
        "reconciliationWarning": mapping.reconciliation_warning,
        "rows": [
            {
                "phase": row.parent_name,
                "task": row.name,
                "taskType": row.task_type,
                "owner": row.owner,
                "shiftDays": row.shift_days,
                "goLiveImpactDays": row.go_live_impact_days,
            }
            for row in mapping.rows
        ],
    }

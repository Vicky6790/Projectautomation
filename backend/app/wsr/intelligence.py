"""Project intelligence and consolidated risk engine for the executive summary."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.models import PlanTaskData, ProjectPlanData, WsrPlanFacts
from app.wsr.detection import go_live_markers, sign_off_markers, upcoming_horizon_days
from app.wsr.facts import (
    _candidate_date,
    _complete,
    _contains,
    _descendants,
    _due_date,
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


def build_executive_summary_input(
    plan: ProjectPlanData,
    facts: WsrPlanFacts,
    as_of: str,
) -> dict[str, Any]:
    as_of_d = date.fromisoformat(as_of)
    phases_rows = select_phase_summaries(plan.tasks, project_name=facts.project_name or plan.name)
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
                    "percentComplete": task.percent_complete,
                }
            )
        elif planned <= horizon:
            upcoming.append(
                {
                    "id": str(task.id),
                    "name": task.name,
                    "plannedDate": planned.isoformat(),
                    "daysToMilestone": (planned - as_of).days,
                    "percentComplete": task.percent_complete,
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
    if task.percent_complete >= 100:
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
    successors: dict[int, list[int]] = defaultdict(list)
    for task in tasks:
        for pred in task.predecessor_ids:
            successors[pred].append(task.id)
    go_live_id = None if go_live is None else go_live.id
    rows: list[dict[str, Any]] = []
    for task in tasks:
        if task.is_summary or not task.predecessor_ids:
            continue
        for pred_id in task.predecessor_ids:
            predecessor = by_id.get(pred_id)
            if predecessor is None:
                continue
            delayed = _is_delayed(predecessor, as_of)
            rows.append(
                {
                    "predecessorId": str(predecessor.id),
                    "predecessorName": predecessor.name,
                    "successorId": str(task.id),
                    "successorName": task.name,
                    "delayed": delayed,
                    "goLiveImpact": _reaches(successors, predecessor.id, go_live_id),
                }
            )
    delayed_first = sorted(rows, key=lambda item: (not item["delayed"], item["predecessorName"]))
    return delayed_first[:40]


def _is_delayed(task: PlanTaskData, as_of: date) -> bool:
    if _complete(task):
        return False
    due = _due_date(task) or _candidate_date(task)
    return due is not None and due < as_of


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
    leaves = [task for task in plan.tasks if not task.is_summary]
    risks: list[dict[str, Any]] = []
    overdue = [
        task
        for task in leaves
        if not _complete(task) and (_due_date(task) or date.max) < as_of
    ]
    if overdue:
        names = [task.name for task in overdue[:6]]
        extra = len(overdue) - len(names)
        evidence = [f"{task.name} is incomplete with finish before {as_of.isoformat()}" for task in overdue[:5]]
        if extra > 0:
            evidence.append(f"{extra} additional incomplete items finished before the as-of date")
        phase = _affected_phase(overdue[0], phases, plan.tasks)
        risks.append(
            {
                "id": "r1-overdue",
                "title": "Overdue work",
                "severity": "high" if len(overdue) > 2 else "medium",
                "evidence": evidence,
                "affectedTasks": names,
                "affectedPhase": phase,
                "goLiveImpact": _tasks_affect_go_live(overdue, go_live, plan.tasks),
                "recommendedMitigation": "Recover overdue incomplete work before successor activities proceed.",
            }
        )
    upcoming_ms = milestones.get("upcoming") or []
    insufficient = [
        item
        for item in upcoming_ms
        if (item.get("percentComplete") or 0) < 50
    ]
    if upcoming_ms:
        evidence = [
            f"{item['name']} is due in {item.get('daysToMilestone')} day(s) and is {item.get('percentComplete') or 0}% complete"
            for item in upcoming_ms[:5]
        ]
        risks.append(
            {
                "id": "r2-upcoming",
                "title": "Upcoming delivery window",
                "severity": "high" if insufficient else "medium",
                "evidence": evidence,
                "affectedTasks": [item["name"] for item in upcoming_ms[:6]],
                "goLiveImpact": any(
                    go_live is not None and item["id"] == str(go_live.id) for item in upcoming_ms
                ),
                "recommendedMitigation": "Focus delivery on incomplete milestones due within the configured upcoming period.",
            }
        )
    delayed_deps = [item for item in dependencies if item["delayed"]]
    if delayed_deps:
        preds = sorted({item["predecessorName"] for item in delayed_deps})
        succs = sorted({item["successorName"] for item in delayed_deps})
        evidence = [
            f"{item['predecessorName']} is delayed and {item['successorName']} depends on it"
            for item in delayed_deps[:5]
        ]
        go_live_hit = any(item["goLiveImpact"] for item in delayed_deps)
        risks.append(
            {
                "id": "r3-dependency",
                "title": "Upstream delay affecting downstream work",
                "severity": "high" if go_live_hit or len(preds) > 1 else "medium",
                "evidence": evidence,
                "affectedTasks": (preds + succs)[:8],
                "goLiveImpact": go_live_hit,
                "recommendedMitigation": "Unblock delayed predecessors so downstream successor activities can proceed.",
            }
        )
    if facts.project_health in {"at_risk", "off_track"} or any(
        phase["status"] in {"at-risk", "off-track"} for phase in phases
    ):
        evidence = [
            f"Project health is {facts.project_health.replace('_', '-')}",
        ]
        slipped = [phase["name"] for phase in phases if phase["status"] in {"at-risk", "off-track"}]
        if slipped:
            evidence.append("Phases with schedule pressure: " + ", ".join(slipped[:5]))
        if overdue:
            evidence.append(f"{len(overdue)} incomplete items have finish dates before the as-of date")
        risks.append(
            {
                "id": "r4-schedule",
                "title": "Schedule pressure",
                "severity": "critical" if facts.project_health == "off_track" else "high",
                "evidence": evidence,
                "affectedTasks": slipped[:6] or [task.name for task in overdue[:4]],
                "goLiveImpact": go_live_date is not None and go_live_date <= as_of + timedelta(days=upcoming_horizon_days()),
                "recommendedMitigation": "Review remaining critical-path work against the planned finish and Go-Live date.",
            }
        )
    if go_live is not None and go_live_date is not None:
        go_live_risks = [
            risk
            for risk in risks
            if risk.get("goLiveImpact")
        ]
        delayed_to_live = [item for item in delayed_deps if item["goLiveImpact"]]
        incomplete_live = not _complete(go_live) and go_live_date < as_of
        if go_live_risks or delayed_to_live or incomplete_live:
            evidence = [f"Go-Live is identified as {go_live.name} on {go_live_date.isoformat()}"]
            if incomplete_live:
                evidence.append("Go-Live is incomplete and earlier than the as-of date")
            for item in delayed_to_live[:3]:
                evidence.append(
                    f"{item['predecessorName']} delay can affect {item['successorName']} on the path to Go-Live"
                )
            risks.append(
                {
                    "id": "r5-go-live",
                    "title": "Go-Live impact",
                    "severity": "critical" if incomplete_live else "high",
                    "evidence": evidence,
                    "affectedTasks": [go_live.name, *[item["predecessorName"] for item in delayed_to_live[:4]]],
                    "goLiveImpact": True,
                    "recommendedMitigation": "Protect the Go-Live path by recovering delayed predecessors first.",
                }
            )
    resource = _resource_health(plan, progress, go_live_date, as_of, facts)
    if resource in {"at-risk", "off-track"} and progress["metric"] == "work":
        remaining = progress["remaining"]
        people = facts.people_planned or facts.resources_deployed
        if isinstance(remaining, (int, float)) and remaining > 0 and people:
            evidence = [
                f"Remaining work is {remaining} hours across leaf tasks",
                f"Named resource count used for capacity is {people}",
            ]
            if go_live_date is not None:
                days = max((go_live_date - as_of).days, 0)
                evidence.append(f"Calendar days from as-of to Go-Live: {days}")
            risks.append(
                {
                    "id": "r6-resource",
                    "title": "Remaining effort pressure",
                    "severity": "medium" if resource == "at-risk" else "high",
                    "evidence": evidence,
                    "goLiveImpact": go_live_date is not None,
                    "recommendedMitigation": "Check remaining effort against available named resources before Go-Live.",
                }
            )
    return risks


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
    overdue = any(
        not _complete(task) and (_due_date(task) or date.max) < as_of for task in leaves
    )
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

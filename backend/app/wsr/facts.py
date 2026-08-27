from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from app.models import (
    MilestoneItem,
    NamedDateValue,
    PhaseStatus,
    PlanTaskData,
    ProgressItem,
    ProjectPlanData,
    WsrPlanFacts,
)
from app.plan.library import PHASES

_GO_LIVE_MARKERS = ("go-live", "go live")
_SIGN_OFF_MARKERS = (
    "sign-off",
    "sign off",
    "review & approval",
    "review and approval",
    "uat sign-off",
    "project plan sign-off",
)
_GATE_NAME_MARKERS = _SIGN_OFF_MARKERS + _GO_LIVE_MARKERS + ("approval",)
_LIBRARY_PHASE_NAMES = frozenset(
    " ".join(str(phase["name"]).casefold().split()) for phase in PHASES
)
_PHASE_WBS = re.compile(r"^1\.\d+$")
_HEALTH_LABELS = {
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
    "unavailable": "Unavailable — insufficient plan data",
}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def resolve_as_of(plan: ProjectPlanData, *, generated_on: date | None = None) -> str:
    parsed = parse_date(plan.status_date)
    return (parsed or generated_on or datetime.now(UTC).date()).isoformat()


def derive_wsr_facts(
    plan: ProjectPlanData,
    as_of: str,
    *,
    generated_at: str | None = None,
) -> WsrPlanFacts:
    as_of_d = date.fromisoformat(as_of)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    stamp = generated_at or now.replace("+00:00", "Z")
    leaves = [task for task in plan.tasks if not task.is_summary]
    go_live = _planned_go_live(leaves, as_of_d)
    health = _health(leaves, as_of_d, go_live)
    countdown = None if go_live is None else (go_live - as_of_d).days
    planned_count = len(leaves) if plan.tasks else None
    completed_count = None
    if planned_count is not None:
        completed_count = sum(1 for task in leaves if _complete(task))
    phases = _phase_statuses(plan)
    overview = _overview(plan, as_of, health, go_live)
    return WsrPlanFacts(
        project_name=plan.name or None,
        project_owner=plan.owner,
        as_of_date=as_of,
        generated_at=stamp,
        project_health=health,
        countdown_days=countdown,
        overall_progress=_overall_progress(leaves),
        planned_work_items=planned_count,
        completed_work_items=completed_count,
        capacity_utilization=_capacity(plan),
        people_planned=_people_planned(plan),
        resources_deployed=_resources_deployed(plan),
        person_days_planned=_person_days(plan),
        phase_count=len(phases) if phases else None,
        last_signed_off_milestone=_last_signed_off(leaves, as_of_d),
        next_gate=_next_gate(leaves, as_of_d),
        planned_go_live_date=None if go_live is None else go_live.isoformat(),
        executive_overview=overview,
        timeline=phases or None,
        phase_statuses=phases,
        progress_to_date=_progress_to_date(leaves, as_of_d),
        upcoming_milestones=_next_planned_tasks(leaves, as_of_d),
    )


def _complete(task: PlanTaskData) -> bool:
    return bool(task.actual_finish) or task.percent_complete >= 100


def _due_date(task: PlanTaskData) -> date | None:
    return parse_date(task.scheduled_finish)


def _candidate_date(task: PlanTaskData) -> date | None:
    return parse_date(task.scheduled_finish) or parse_date(task.scheduled_start)


def _contains(text: str | None, markers: tuple[str, ...]) -> bool:
    haystack = (text or "").lower()
    return any(marker in haystack for marker in markers)


def _planned_go_live(tasks: list[PlanTaskData], as_of: date) -> date | None:
    incomplete = [
        task
        for task in tasks
        if not _complete(task) and _candidate_date(task) is not None
    ]
    for matcher in (
        lambda task: _contains(task.gate, _GO_LIVE_MARKERS),
        lambda task: _contains(task.name, _GO_LIVE_MARKERS),
        lambda task: task.is_milestone,
    ):
        matched = [task for task in incomplete if matcher(task)]
        if not matched:
            continue
        future = [
            task
            for task in matched
            if (_candidate_date(task) or date.min) >= as_of
        ]
        pool = future or matched
        dates = [_candidate_date(task) for task in pool]
        return min(item for item in dates if item is not None)
    return None


def _health(
    tasks: list[PlanTaskData],
    as_of: date,
    go_live: date | None,
) -> str:
    if go_live is None:
        return "unavailable"
    if go_live < as_of:
        return "off_track"
    dated = [task for task in tasks if _due_date(task) is not None]
    progressed = [
        task
        for task in tasks
        if task.percent_complete or task.actual_start or task.actual_finish
    ]
    if not dated and not progressed:
        return "unavailable"
    overdue = False
    for task in dated:
        due = _due_date(task)
        if due is not None and not _complete(task) and due < as_of:
            overdue = True
            break
    return "at_risk" if overdue else "on_track"


def _overall_progress(tasks: list[PlanTaskData]) -> float | None:
    work = [
        (task.percent_complete, task.planned_work_hours)
        for task in tasks
        if task.planned_work_hours
    ]
    if work:
        total = sum(hours for _pct, hours in work)
        if total <= 0:
            return None
        return round(sum(pct * hours for pct, hours in work) / total, 1)
    durations: list[tuple[float, float]] = []
    for task in tasks:
        start = parse_date(task.scheduled_start)
        finish = parse_date(task.scheduled_finish)
        if start is None or finish is None or finish < start:
            continue
        days = (finish - start).days or 1
        durations.append((task.percent_complete, float(days)))
    if not durations:
        return None
    total = sum(days for _pct, days in durations)
    return round(sum(pct * days for pct, days in durations) / total, 1)


def _capacity(plan: ProjectPlanData) -> float | None:
    planned = 0.0
    actual = 0.0
    has_planned = False
    for task in plan.tasks:
        if task.is_summary:
            continue
        assignment_planned = False
        for item in task.assignments:
            if item.planned_work_hours:
                planned += item.planned_work_hours
                has_planned = True
                assignment_planned = True
            if item.actual_work_hours:
                actual += item.actual_work_hours
        if assignment_planned:
            continue
        if task.planned_work_hours:
            planned += task.planned_work_hours
            has_planned = True
        if task.actual_work_hours:
            actual += task.actual_work_hours
    if not has_planned or planned <= 0:
        return None
    return round(min(100.0, max(0.0, actual / planned * 100)), 1)


def _person_days(plan: ProjectPlanData) -> float | None:
    hours = 0.0
    found = False
    for task in plan.tasks:
        if task.is_summary:
            continue
        task_hours = 0.0
        for item in task.assignments:
            if item.planned_work_hours:
                task_hours += item.planned_work_hours
                found = True
        if not task_hours and task.planned_work_hours:
            task_hours = task.planned_work_hours
            found = True
        hours += task_hours
    if not found:
        return None
    return round(hours / 8.0, 1)


def _people_planned(plan: ProjectPlanData) -> int | None:
    names = {
        item.resource_id or item.resource_name
        for task in plan.tasks
        for item in task.assignments
    }
    return len(names) if names else None


def _resources_deployed(plan: ProjectPlanData) -> int | None:
    names = {item.id for item in plan.resources if (item.name or "").strip()}
    return len(names) if names else None


def _last_signed_off(tasks: list[PlanTaskData], as_of: date) -> NamedDateValue | None:
    completed = [
        task
        for task in tasks
        if _complete(task)
        and _candidate_date(task) is not None
        and _candidate_date(task) <= as_of
    ]
    for matcher in (
        lambda task: bool((task.gate or "").strip()),
        lambda task: task.is_milestone,
        lambda task: _contains(task.name, _SIGN_OFF_MARKERS),
    ):
        matched = [task for task in completed if matcher(task)]
        if matched:
            latest = max(matched, key=lambda task: _candidate_date(task) or date.min)
            when = _candidate_date(latest) or as_of
            return NamedDateValue(name=latest.name, date=when.isoformat())
    return None


def _next_gate(tasks: list[PlanTaskData], as_of: date) -> NamedDateValue | None:
    incomplete = [
        task
        for task in tasks
        if not _complete(task)
        and _candidate_date(task) is not None
        and _candidate_date(task) >= as_of
    ]
    for matcher in (
        lambda task: bool((task.gate or "").strip()),
        lambda task: task.is_milestone,
        lambda task: _contains(task.name, _GATE_NAME_MARKERS),
    ):
        matched = [task for task in incomplete if matcher(task)]
        if matched:
            earliest = min(matched, key=lambda task: _candidate_date(task) or date.max)
            return NamedDateValue(
                name=earliest.name,
                date=(_candidate_date(earliest) or as_of).isoformat(),
            )
    return None


def select_phase_summaries(
    tasks: list[PlanTaskData],
    project_name: str | None = None,
) -> list[PlanTaskData]:
    """Select phase rows from WBS 1.x, then naming convention, then outline.

    WBS ``1`` is the project name. Direct codes ``1.1``, ``1.2``, ``1.3``,
    ``1.5`` (and any other ``1.<n>``) are phases. Subtasks such as ``1.1.1``
    are not. Generated plans without those codes still use name/outline rules.
    """
    if not tasks:
        return []
    wbs_phases = _wbs_phase_rows(tasks)
    if wbs_phases:
        return wbs_phases

    parent = _project_parent(tasks, project_name)
    scope = _descendants(tasks, parent) if parent is not None else list(tasks)
    named = _named_phase_rows(tasks, scope)
    if named:
        return named

    if parent is not None:
        nested = _direct_children(tasks, parent)
        if nested:
            return nested

    summaries = [task for task in tasks if task.is_summary]
    if not summaries:
        return []

    min_level = min(task.outline_level for task in summaries)
    roots = [task for task in tasks if task.is_summary and task.outline_level == min_level]
    if len(roots) == 1:
        nested = _direct_children(tasks, roots[0])
        return nested or roots
    return roots


def _wbs_phase_rows(tasks: list[PlanTaskData]) -> list[PlanTaskData]:
    matched = [task for task in tasks if _is_phase_wbs(task.wbs)]
    matched.sort(key=lambda task: (_wbs_index(task.wbs), task.id))
    return matched


def _is_phase_wbs(value: str | None) -> bool:
    return bool(_PHASE_WBS.match((value or "").strip()))


def _wbs_index(value: str | None) -> int:
    try:
        return int((value or "").strip().split(".")[1])
    except (IndexError, ValueError):
        return 0


def _named_phase_rows(
    tasks: list[PlanTaskData],
    scope: list[PlanTaskData],
) -> list[PlanTaskData]:
    candidates = [task for task in scope if _matches_phase_convention(task)]
    selected: list[PlanTaskData] = []
    for task in candidates:
        if any(_is_under(tasks, parent, task) for parent in selected):
            continue
        selected.append(task)
    return selected


def _matches_phase_convention(task: PlanTaskData) -> bool:
    if _is_phase_named(task.name):
        return True
    if _contains(task.name, _GO_LIVE_MARKERS):
        return True
    return _norm_name(task.name) in _LIBRARY_PHASE_NAMES


def _is_phase_named(name: str | None) -> bool:
    text = _norm_name(name)
    if "(" in text:
        text = text[: text.index("(")].strip()
    words = text.split()
    if not words:
        return False
    return words[0] == "phase" or words[-1] == "phase"


def _is_under(tasks: list[PlanTaskData], parent: PlanTaskData, child: PlanTaskData) -> bool:
    return any(item.id == child.id for item in _descendants(tasks, parent))


def _project_parent(tasks: list[PlanTaskData], project_name: str | None) -> PlanTaskData | None:
    wanted = _norm_name(project_name)
    if not wanted:
        return None
    exact = [
        task
        for task in tasks
        if task.is_summary and _norm_name(task.name) == wanted
    ]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return min(exact, key=lambda task: (task.outline_level, task.id))
    contains = [
        task
        for task in tasks
        if task.is_summary
        and (wanted in _norm_name(task.name) or _norm_name(task.name) in wanted)
        and _norm_name(task.name)
    ]
    if len(contains) == 1:
        return contains[0]
    if contains:
        return min(contains, key=lambda task: (task.outline_level, task.id))
    return None


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _direct_children(tasks: list[PlanTaskData], parent: PlanTaskData) -> list[PlanTaskData]:
    start = next((index for index, task in enumerate(tasks) if task.id == parent.id), None)
    if start is None:
        return []
    children: list[PlanTaskData] = []
    for task in tasks[start + 1 :]:
        if task.outline_level <= parent.outline_level:
            break
        if task.outline_level == parent.outline_level + 1:
            children.append(task)
    return children


def _descendants(tasks: list[PlanTaskData], parent: PlanTaskData) -> list[PlanTaskData]:
    start = next((index for index, task in enumerate(tasks) if task.id == parent.id), None)
    if start is None:
        return []
    children: list[PlanTaskData] = []
    for task in tasks[start + 1 :]:
        if task.outline_level <= parent.outline_level:
            break
        children.append(task)
    return children


def _phase_statuses(plan: ProjectPlanData) -> list[PhaseStatus]:
    rows = select_phase_summaries(plan.tasks, project_name=plan.name)
    if rows:
        return [_phase_from_task(plan.tasks, row) for row in rows]
    return [_phase_status(phase) for phase in plan.phases]


def _phase_from_task(tasks: list[PlanTaskData], phase: PlanTaskData) -> PhaseStatus:
    children = _descendants(tasks, phase)
    leaves = [task for task in children if not task.is_summary] or children
    dated = [phase, *leaves]
    starts = [parse_date(task.scheduled_start) for task in dated]
    finishes = [parse_date(task.scheduled_finish) for task in dated]
    actual_starts = [parse_date(task.actual_start) for task in dated]
    actual_finishes = [parse_date(task.actual_finish) for task in dated]
    start_ok = [item for item in starts if item]
    finish_ok = [item for item in finishes if item]
    actual_start_ok = [item for item in actual_starts if item]
    actual_finish_ok = [item for item in actual_finishes if item]
    if phase.percent_complete >= 100:
        state = "complete"
    elif not phase.actual_start and phase.percent_complete == 0:
        if any(task.percent_complete or task.actual_start for task in leaves):
            state = "in_progress"
        else:
            state = "not_started"
    else:
        state = "in_progress"
    return PhaseStatus(
        name=phase.name,
        wbs=(phase.wbs or "").strip() or None,
        planned_start=None if not start_ok else min(start_ok).isoformat(),
        planned_finish=None if not finish_ok else max(finish_ok).isoformat(),
        actual_start=None if not actual_start_ok else min(actual_start_ok).isoformat(),
        actual_finish=None if not actual_finish_ok else max(actual_finish_ok).isoformat(),
        progress=phase.percent_complete,
        state=state,
    )


def _phase_status(phase) -> PhaseStatus:
    if phase.percent_complete >= 100:
        state = "complete"
    elif not phase.actual_start and phase.percent_complete == 0:
        state = "not_started"
    else:
        state = "in_progress"
    return PhaseStatus(
        name=phase.name,
        wbs=getattr(phase, "wbs", None),
        planned_start=phase.scheduled_start,
        planned_finish=phase.scheduled_finish,
        actual_start=phase.actual_start,
        actual_finish=None,
        progress=phase.percent_complete,
        state=state,
    )


def _week_bounds(as_of: date) -> tuple[date, date]:
    start = as_of - timedelta(days=as_of.weekday())
    return start, start + timedelta(days=6)


def _overlaps_week(task: PlanTaskData, week_start: date, week_end: date) -> bool:
    start = parse_date(task.scheduled_start) or parse_date(task.actual_start)
    finish = parse_date(task.scheduled_finish) or parse_date(task.actual_finish)
    if start is None and finish is None:
        return False
    start = start or finish
    finish = finish or start
    return start <= week_end and finish >= week_start


def _progress_to_date(tasks: list[PlanTaskData], as_of: date) -> list[ProgressItem]:
    week_start, week_end = _week_bounds(as_of)
    items: list[ProgressItem] = []
    for task in tasks:
        if not _overlaps_week(task, week_start, week_end):
            continue
        when = _candidate_date(task)
        items.append(
            ProgressItem(
                name=task.name,
                date=None if when is None else when.isoformat(),
                progress=task.percent_complete,
            )
        )
    return items


def _next_planned_tasks(tasks: list[PlanTaskData], as_of: date) -> list[MilestoneItem]:
    _week_start, week_end = _week_bounds(as_of)
    items: list[MilestoneItem] = []
    for task in tasks:
        if _complete(task):
            continue
        start = parse_date(task.scheduled_start)
        finish = parse_date(task.scheduled_finish)
        when = start or finish
        if when is None or when <= week_end:
            continue
        items.append(MilestoneItem(name=task.name, date=when.isoformat()))
    items.sort(key=lambda item: item.date or "")
    return items[:12]


def _overview(plan: ProjectPlanData, as_of: str, health: str, go_live: date | None) -> str | None:
    name = plan.name or None
    if not name and health == "unavailable" and go_live is None:
        return None
    label = _HEALTH_LABELS[health]
    go_live_text = go_live.isoformat() if go_live else "unavailable"
    title = name or "This project"
    return f"{title} is {label} as of {as_of}. Planned Go-Live is {go_live_text}."


def next_seven_day_tasks(plan: ProjectPlanData, as_of: str) -> list[PlanTaskData]:
    as_of_d = date.fromisoformat(as_of)
    horizon = as_of_d + timedelta(days=7)
    due: list[PlanTaskData] = []
    for task in plan.tasks:
        if task.is_summary or _complete(task):
            continue
        finish = _due_date(task) or _candidate_date(task)
        if finish and as_of_d < finish <= horizon:
            due.append(task)
    return due

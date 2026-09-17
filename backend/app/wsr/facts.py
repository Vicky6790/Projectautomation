from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.config import settings
from app.models import (
    MilestoneItem,
    NamedDateValue,
    PhaseStatus,
    PlanTaskData,
    PortfolioSummary,
    ProgressItem,
    ProjectPlanData,
    WsrPlanFacts,
)
from app.plan.library import PHASES
from app.wsr.detection import (
    gate_name_markers,
    go_live_markers,
    sign_off_markers,
)
from app.wsr.outline import is_phase_code, is_portfolio_code, is_project_code, parse_outline_code

_LIBRARY_PHASE_NAMES = frozenset(
    " ".join(str(phase["name"]).casefold().split()) for phase in PHASES
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        return None


def resolve_as_of(plan: ProjectPlanData, *, generated_on: date | None = None) -> str:
    parsed = parse_date(plan.status_date)
    return (parsed or generated_on or datetime.now(UTC).date()).isoformat()


def wsr_publish_date(*, generated_on: date | None = None) -> str:
    """System date when the WSR is generated, unless WSR_REPORT_DATE is set."""
    if generated_on is None:
        override = parse_date((settings.wsr_report_date or "").strip() or None)
        if override is not None:
            return override.isoformat()
    return (generated_on or datetime.now(UTC).date()).isoformat()


def reporting_windows(report_date: date) -> tuple[date, date, date, date]:
    """Inclusive current week and upcoming 7-day windows from a frozen report date.

    Current week is the 7 calendar days ending on reportDate (reportDate-6 .. reportDate).
    Upcoming is the next 7 calendar days (reportDate+1 .. reportDate+7).
    """
    current_start = report_date - timedelta(days=6)
    current_end = report_date
    upcoming_start = report_date + timedelta(days=1)
    upcoming_end = report_date + timedelta(days=7)
    return current_start, current_end, upcoming_start, upcoming_end


def derive_wsr_facts(
    plan: ProjectPlanData,
    as_of: str,
    *,
    generated_at: str | None = None,
    project_code: str | None = None,
) -> WsrPlanFacts:
    as_of_d = date.fromisoformat(as_of)
    current_start, current_end, upcoming_start, upcoming_end = reporting_windows(as_of_d)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    stamp = generated_at or now.replace("+00:00", "Z")
    leaves = [task for task in plan.tasks if not task.is_summary]
    go_live = _planned_go_live(plan.tasks, as_of_d)
    health = _health(leaves, as_of_d, go_live)
    countdown = None if go_live is None else (go_live - as_of_d).days
    planned_count = len(leaves) if plan.tasks else None
    completed_count = None
    if planned_count is not None:
        completed_count = sum(1 for task in leaves if _complete(task))
    title = _project_title(plan, project_code)
    phases = _phase_statuses(plan, project_name=title, project_code=project_code)
    phase_ids = _phase_ids(plan, title, project_code)
    progress = _overall_progress(leaves)
    if progress is None:
        wanted = (project_code or "1").strip()
        row = next((task for task in plan.tasks if (task.wbs or "").strip() == wanted), None)
        if row is not None:
            progress = float(row.percent_complete)
    return WsrPlanFacts(
        project_code=project_code,
        project_name=title,
        project_owner=plan.owner,
        as_of_date=as_of,
        report_date=as_of,
        current_week_start=current_start.isoformat(),
        current_week_end=current_end.isoformat(),
        upcoming_start=upcoming_start.isoformat(),
        upcoming_end=upcoming_end.isoformat(),
        generated_at=stamp,
        project_health=health,
        countdown_days=countdown,
        overall_progress=progress,
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
        executive_overview=None,
        timeline=phases or None,
        phase_statuses=phases,
        delay_mapping=_delay_mapping(plan, as_of_d, phases, go_live),
        progress_to_date=_progress_to_date(leaves, plan.tasks, as_of_d, phase_ids),
        upcoming_milestones=_next_planned_tasks(leaves, plan.tasks, as_of_d, phase_ids),
    )


def derive_portfolio_summary(plan: ProjectPlanData, as_of: str) -> PortfolioSummary:
    """Name, countdown, and overall % from WBS 0 using the same WSR rules as a project row."""

    as_of_d = date.fromisoformat(as_of)
    row = next((task for task in plan.tasks if (task.wbs or "").strip() == "0"), None)
    leaves = [task for task in plan.tasks if not task.is_summary]
    go_live = _planned_go_live(plan.tasks, as_of_d)
    if go_live is None and row is not None:
        go_live = _candidate_date(row)
    progress = _overall_progress(leaves)
    if progress is None and row is not None:
        progress = float(row.percent_complete)
    name = (row.name or "").strip() if row is not None else ""
    return PortfolioSummary(
        name=name or _project_title(plan, "0"),
        countdown_days=None if go_live is None else (go_live - as_of_d).days,
        overall_progress=progress,
        planned_go_live_date=None if go_live is None else go_live.isoformat(),
    )


def _normalized_percent(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return 0.0
    # MSP/MPXJ store 0–100. 1 means 1%, not 100%. Only (0, 1) is a fraction.
    if 0 < pct < 1.0:
        return pct * 100.0
    return pct


def _complete(task: PlanTaskData) -> bool:
    if task.actual_finish:
        return True
    return _normalized_percent(task.percent_complete) >= 99.5


def _due_date(task: PlanTaskData) -> date | None:
    return parse_date(task.scheduled_finish)


def _candidate_date(task: PlanTaskData) -> date | None:
    return parse_date(task.scheduled_finish) or parse_date(task.scheduled_start)


def _contains(text: str | None, markers: tuple[str, ...]) -> bool:
    haystack = (text or "").lower()
    return any(marker in haystack for marker in markers)


def _planned_go_live(tasks: list[PlanTaskData], as_of: date) -> date | None:
    named = [
        task
        for task in tasks
        if _contains(task.gate, go_live_markers()) or _contains(task.name, go_live_markers())
    ]
    dates = [item for item in (_candidate_date(task) for task in named) if item is not None]
    if not dates:
        return None
    future = [item for item in dates if item >= as_of]
    return min(future) if future else max(dates)


def _project_title(plan: ProjectPlanData, project_code: str | None = None) -> str | None:
    wanted = (project_code or "1").strip()
    for task in plan.tasks:
        if (task.wbs or "").strip() == wanted:
            name = (task.name or "").strip()
            if name:
                return name
    return plan.name or None


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


def work_based_progress(tasks: list[PlanTaskData]) -> dict[str, float | str | None]:
    """Leaf actual work / planned work. Does not convert duration into work."""

    planned = 0.0
    actual = 0.0
    remaining = 0.0
    paired = False
    for task in tasks:
        if task.is_summary:
            continue
        planned_hours, actual_hours = _leaf_work_hours(task)
        if not planned_hours or planned_hours <= 0 or actual_hours is None:
            continue
        paired = True
        planned += planned_hours
        actual += actual_hours
        remaining += max(0.0, planned_hours - actual_hours)
    if not paired or planned <= 0:
        return {
            "metric": "unavailable",
            "overall_percent": None,
            "planned": None,
            "actual": None,
            "remaining": None,
        }
    return {
        "metric": "work",
        "overall_percent": round(actual / planned * 100, 1),
        "planned": round(planned, 1),
        "actual": round(actual, 1),
        "remaining": round(remaining, 1),
    }


def _leaf_work_hours(task: PlanTaskData) -> tuple[float | None, float | None]:
    planned = task.planned_work_hours
    actual = task.actual_work_hours
    if planned is None:
        assignment_planned = [
            item.planned_work_hours for item in task.assignments if item.planned_work_hours
        ]
        planned = sum(assignment_planned) if assignment_planned else None
    if actual is None:
        assignment_actual = [
            item.actual_work_hours for item in task.assignments if item.actual_work_hours is not None
        ]
        actual = sum(assignment_actual) if assignment_actual else None
    return planned, actual


def _overall_progress(tasks: list[PlanTaskData]) -> float | None:
    percent = work_based_progress(tasks)["overall_percent"]
    return None if percent is None else float(percent)


def _work_complete_percent(task: PlanTaskData) -> float | None:
    """Phase % from the MPP % Work Complete column on that row."""

    if task.percent_work_complete is not None:
        return round(min(100.0, max(0.0, _normalized_percent(task.percent_work_complete))), 1)
    planned = task.planned_work_hours
    actual = task.actual_work_hours
    if planned and planned > 0 and actual is not None:
        return round(min(100.0, max(0.0, actual / planned * 100)), 1)
    return None


def _phase_state_from_progress(phase: PlanTaskData, progress: float | None) -> str:
    if progress is not None and progress >= 99.5:
        return "complete"
    if (progress or 0) > 0 or bool(phase.actual_start):
        return "in_progress"
    return "not_started"


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
        lambda task: _contains(task.name, sign_off_markers()),
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
        lambda task: _contains(task.name, gate_name_markers()),
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
    *,
    project_code: str | None = None,
) -> list[PlanTaskData]:
    """Select phase rows from WBS N.x, then naming convention, then outline.

    Outline ``0`` is the parent of all projects. A single integer (``1``, ``2``)
    is a project name. Direct codes ``1.1`` / ``2.1`` are phases of that
    project. Subtasks such as ``1.1.1`` are not. Generated plans without those
    codes still use name/outline rules.
    """
    if not tasks:
        return []
    wbs_phases = _wbs_phase_rows(tasks, project_code=project_code)
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


def _wbs_phase_rows(
    tasks: list[PlanTaskData],
    *,
    project_code: str | None = None,
) -> list[PlanTaskData]:
    matched = [task for task in tasks if is_phase_code(task.wbs, project_code)]
    matched.sort(key=lambda task: (_wbs_index(task.wbs), task.id))
    return matched


def _wbs_index(value: str | None) -> int:
    parts = parse_outline_code(value) or (0,)
    return parts[1] if len(parts) >= 2 else 0


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
    if _contains(task.name, go_live_markers()):
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


def _phase_statuses(
    plan: ProjectPlanData,
    *,
    project_name: str | None = None,
    project_code: str | None = None,
) -> list[PhaseStatus]:
    rows = select_phase_summaries(
        plan.tasks,
        project_name=project_name or plan.name,
        project_code=project_code,
    )
    if rows:
        return [_phase_from_task(plan.tasks, row) for row in rows]
    return [_phase_status(phase) for phase in plan.phases]


def _under_phase(tasks: list[PlanTaskData], phase: PlanTaskData) -> list[PlanTaskData]:
    outlined = _descendants(tasks, phase)
    if outlined:
        return outlined
    prefix = (phase.wbs or "").strip()
    if not prefix:
        return []
    nested = prefix + "."
    return [task for task in tasks if task.id != phase.id and (task.wbs or "").strip().startswith(nested)]


def _phase_from_task(tasks: list[PlanTaskData], phase: PlanTaskData) -> PhaseStatus:
    children = _under_phase(tasks, phase)
    leaves = [task for task in children if not task.is_summary] or children
    dated = [phase, *leaves]
    baseline_starts = [parse_date(task.baseline_start) for task in dated]
    baseline_finishes = [parse_date(task.baseline_finish) for task in dated]
    current_starts = [parse_date(task.scheduled_start) for task in dated]
    current_finishes = [parse_date(task.scheduled_finish) for task in dated]
    baseline_start_ok = [item for item in baseline_starts if item]
    baseline_finish_ok = [item for item in baseline_finishes if item]
    current_start_ok = [item for item in current_starts if item]
    current_finish_ok = [item for item in current_finishes if item]
    progress = _work_complete_percent(phase)
    return PhaseStatus(
        name=phase.name,
        wbs=(phase.wbs or "").strip() or None,
        planned_start=None if not baseline_start_ok else min(baseline_start_ok).isoformat(),
        planned_finish=None if not baseline_finish_ok else max(baseline_finish_ok).isoformat(),
        actual_start=None if not current_start_ok else min(current_start_ok).isoformat(),
        actual_finish=None if not current_finish_ok else max(current_finish_ok).isoformat(),
        progress=progress,
        state=_phase_state_from_progress(phase, progress),
    )


def _phase_status(phase) -> PhaseStatus:
    progress = _work_complete_percent(phase)
    return PhaseStatus(
        name=phase.name,
        wbs=getattr(phase, "wbs", None),
        planned_start=phase.baseline_start,
        planned_finish=phase.baseline_finish,
        actual_start=phase.scheduled_start,
        actual_finish=phase.scheduled_finish,
        progress=progress,
        state=_phase_state_from_progress(phase, progress),
    )


def delay_mapping_from_plans(
    current: ProjectPlanData,
    baseline: ProjectPlanData | None = None,
):
    as_of_d = date.fromisoformat(wsr_publish_date())
    phases = _phase_statuses(current)
    go_live = _planned_go_live(current.tasks, as_of_d)
    return _delay_mapping(current, as_of_d, phases, go_live, baseline_plan=baseline)


def _delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,
    baseline_plan: ProjectPlanData | None = None,
):
    from app.wsr.delay_engine import build_delay_mapping

    return build_delay_mapping(plan, as_of, phases, go_live_date, baseline_plan=baseline_plan)


def _phase_ids(plan: ProjectPlanData, project_name: str | None, project_code: str | None) -> set[int]:
    rows = select_phase_summaries(
        plan.tasks,
        project_name=project_name or plan.name,
        project_code=project_code,
    )
    return {row.id for row in rows}


def _phase_and_parent(
    task: PlanTaskData,
    tasks: list[PlanTaskData],
    phase_ids: set[int],
) -> tuple[str | None, str | None]:
    ancestors = _ancestors(task, tasks)
    parent = next((item for item in ancestors if not _is_project_container(item)), None)
    phase = next((item for item in ancestors if item.id in phase_ids), None)
    if phase is None:
        phase = next((item for item in ancestors if is_phase_code(item.wbs)), None)
    return _clean_name(None if phase is None else phase.name), _clean_name(
        None if parent is None else parent.name
    )


def _ancestors(task: PlanTaskData, tasks: list[PlanTaskData]) -> list[PlanTaskData]:
    """Nearest parent first."""
    wbs_map = {(item.wbs or "").strip(): item for item in tasks if (item.wbs or "").strip()}
    code = (task.wbs or "").strip()
    found: list[PlanTaskData] = []
    while "." in code:
        code = code.rsplit(".", 1)[0]
        parent = wbs_map.get(code)
        if parent is not None:
            found.append(parent)
    if found:
        return found
    index = next((i for i, item in enumerate(tasks) if item.id == task.id), None)
    if index is None:
        return []
    level = task.outline_level
    chain: list[PlanTaskData] = []
    for prev in reversed(tasks[:index]):
        if prev.outline_level < level:
            chain.append(prev)
            level = prev.outline_level
    return chain


def _is_project_container(task: PlanTaskData) -> bool:
    return is_portfolio_code(task.wbs) or is_project_code(task.wbs)


def _clean_name(value: str | None) -> str | None:
    text = " ".join((value or "").split())
    return text or None


def _join_hierarchy(*parts: str | None) -> str:
    seen: list[str] = []
    for part in parts:
        text = _clean_name(part)
        if not text:
            continue
        if seen and _norm_name(text) == _norm_name(seen[-1]):
            continue
        seen.append(text)
    return " / ".join(seen)


def task_labeler(
    tasks: list[PlanTaskData],
    *,
    project_name: str | None = None,
    project_code: str | None = None,
):
    """Return phase / parent / task labels for WSR risk and week copy."""

    phase_ids = {
        row.id
        for row in select_phase_summaries(
            tasks,
            project_name=project_name,
            project_code=project_code,
        )
    }

    def label(task: PlanTaskData) -> str:
        phase_name, parent_name = _phase_and_parent(task, tasks, phase_ids)
        return _join_hierarchy(phase_name, parent_name, task.name) or task.name

    return label


def _week_bounds(as_of: date) -> tuple[date, date]:
    current_start, current_end, _upcoming_start, _upcoming_end = reporting_windows(as_of)
    return current_start, current_end


def _next_week_bounds(as_of: date) -> tuple[date, date]:
    _current_start, _current_end, upcoming_start, upcoming_end = reporting_windows(as_of)
    return upcoming_start, upcoming_end


def _current_schedule_span(task: PlanTaskData) -> tuple[date, date] | None:
    start = parse_date(task.scheduled_start) or parse_date(task.actual_start)
    finish = parse_date(task.scheduled_finish) or parse_date(task.actual_finish)
    if start is None and finish is None:
        return None
    start = start or finish
    finish = finish or start
    if finish < start:
        start, finish = finish, start
    return start, finish


def _overlaps_window(span: tuple[date, date] | None, week_start: date, week_end: date) -> bool:
    if span is None:
        return False
    start, finish = span
    return start <= week_end and finish >= week_start


def _in_current_week(task: PlanTaskData, week_start: date, week_end: date) -> bool:
    if _overlaps_window(_current_schedule_span(task), week_start, week_end):
        return True
    actual_finish = parse_date(task.actual_finish)
    return actual_finish is not None and week_start <= actual_finish <= week_end


def _planned_or_current_finish(task: PlanTaskData) -> date | None:
    return parse_date(task.scheduled_finish) or parse_date(task.actual_finish)


def _is_milestone_like(task: PlanTaskData) -> bool:
    if task.is_summary:
        return False
    if task.is_milestone or (task.gate or "").strip():
        return True
    return _contains(task.name, go_live_markers()) or _contains(task.name, sign_off_markers())


def _dedupe_week_items(items: list, *, by_name_only: bool = False):
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for item in items:
        name = _norm_name(item.name)
        if not name:
            continue
        if by_name_only:
            key = (name, "", "")
        else:
            key = (name, item.scheduled_start or "", item.scheduled_finish or item.date or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _task_owner_label(task: PlanTaskData, all_tasks: list[PlanTaskData]) -> str | None:
    from app.wsr.delay_engine import _resolved_owner_names

    names = _resolved_owner_names(task, all_tasks)
    return " & ".join(names) if names else None


def _progress_item(task: PlanTaskData, all_tasks: list[PlanTaskData], phase_ids: set[int]) -> ProgressItem:
    when = _candidate_date(task)
    phase_name, parent_name = _phase_and_parent(task, all_tasks, phase_ids)
    return ProgressItem(
        name=task.name,
        date=None if when is None else when.isoformat(),
        scheduled_start=task.scheduled_start,
        scheduled_finish=task.scheduled_finish,
        progress=task.percent_complete,
        phase_name=phase_name,
        parent_name=parent_name,
        label=_join_hierarchy(phase_name, parent_name, task.name),
        owner=_task_owner_label(task, all_tasks),
    )


def _milestone_item(
    task: PlanTaskData,
    all_tasks: list[PlanTaskData],
    phase_ids: set[int],
    finish: date | None,
) -> MilestoneItem:
    when = finish or _candidate_date(task)
    phase_name, parent_name = _phase_and_parent(task, all_tasks, phase_ids)
    return MilestoneItem(
        name=task.name,
        date=None if when is None else when.isoformat(),
        scheduled_start=task.scheduled_start,
        scheduled_finish=task.scheduled_finish,
        phase_name=phase_name,
        parent_name=parent_name,
        label=_join_hierarchy(phase_name, parent_name, task.name),
        owner=_task_owner_label(task, all_tasks),
    )


def _progress_to_date(
    tasks: list[PlanTaskData],
    all_tasks: list[PlanTaskData],
    as_of: date,
    phase_ids: set[int],
) -> list[ProgressItem]:
    week_start, week_end = _week_bounds(as_of)
    items: list[ProgressItem] = []
    for task in tasks:
        if not _in_current_week(task, week_start, week_end):
            continue
        items.append(_progress_item(task, all_tasks, phase_ids))
    items.sort(
        key=lambda item: (
            item.scheduled_start or item.scheduled_finish or item.date or "",
            -(item.progress or 0),
            item.name,
        )
    )
    return _dedupe_week_items(items)


def _next_planned_tasks(
    tasks: list[PlanTaskData],
    all_tasks: list[PlanTaskData],
    as_of: date,
    phase_ids: set[int],
) -> list[MilestoneItem]:
    current_start, current_end = _week_bounds(as_of)
    upcoming_start, upcoming_end = _next_week_bounds(as_of)
    items: list[tuple[MilestoneItem, bool]] = []
    for task in tasks:
        if _complete(task):
            continue
        span = _current_schedule_span(task)
        finish = _planned_or_current_finish(task)
        in_current = _in_current_week(task, current_start, current_end)
        finish_in_upcoming = finish is not None and upcoming_start <= finish <= upcoming_end
        overlaps_upcoming = _overlaps_window(span, upcoming_start, upcoming_end)
        milestone = _is_milestone_like(task)
        if milestone:
            if not finish_in_upcoming:
                continue
        elif in_current or not overlaps_upcoming:
            continue
        items.append((_milestone_item(task, all_tasks, phase_ids, finish), milestone))
    items.sort(
        key=lambda pair: pair[0].scheduled_start or pair[0].scheduled_finish or pair[0].date or ""
    )
    collapsed: list[MilestoneItem] = []
    seen_milestones: set[str] = set()
    seen_rows: set[tuple[str, str, str]] = set()
    for item, milestone in items:
        name = _norm_name(item.name)
        if milestone:
            if name in seen_milestones:
                continue
            seen_milestones.add(name)
            collapsed.append(item)
            continue
        key = (name, item.scheduled_start or "", item.scheduled_finish or item.date or "")
        if key in seen_rows:
            continue
        seen_rows.add(key)
        collapsed.append(item)
    return collapsed


def next_seven_day_tasks(plan: ProjectPlanData, as_of: str) -> list[PlanTaskData]:
    as_of_d = date.fromisoformat(as_of)
    upcoming_start, upcoming_end = _next_week_bounds(as_of_d)
    due: list[PlanTaskData] = []
    for task in plan.tasks:
        if task.is_summary or _complete(task):
            continue
        finish = _due_date(task) or _candidate_date(task)
        if finish and upcoming_start <= finish <= upcoming_end:
            due.append(task)
    return due

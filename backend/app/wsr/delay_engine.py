"""Deterministic Go-Live delay mapping. Dates and days are never invented or AI-calculated."""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.models import (
    DelayMappingRow,
    DelayMappingSheet,
    PhaseStatus,
    PlanTaskData,
    ProjectPlanData,
)
from app.wsr.detection import (
    client_owner_markers,
    go_live_markers,
    internal_owner_markers,
)

_RECONCILE_WARNING = (
    "Delay mapping total does not reconcile with the calculated Go-Live shift. "
    "PM validation required."
)
_EXPLICIT_GO_LIVE = frozenset({"go_live", "go-live", "go live", "golive"})
_EXPLICIT_ADDITIONAL = frozenset({"additional", "unplanned", "additional_scope"})
_DELAY_WORD = re.compile(r"\bdelay\b", re.I)
_ADDITIONAL_WORD = re.compile(r"\badditional\b", re.I)


def build_delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,  # kept for the facts wrapper; header uses milestone finish dates
    baseline_plan: ProjectPlanData | None = None,
) -> DelayMappingSheet:
    """Compare baseline vs current schedules and attribute incremental Go-Live impact.

    A single uploaded MPP already carries MS Project baseline fields; those are the
    baseline snapshot. An optional second plan can be supplied for a two-file compare.
    Current and baseline Go-Live dates always come from the milestone finish fields.
    """

    from app.wsr.facts import (
        _candidate_date,
        _contains,
        parse_date,
        select_phase_summaries,
    )

    current_plan = plan
    _ = go_live_date
    holidays = _holiday_set(current_plan, parse_date)
    calendar_source = (
        "project"
        if (current_plan.calendar_available or current_plan.holiday_dates)
        else "weekdays_fallback"
    )
    go_live_task = _named_go_live_task(current_plan.tasks, as_of, _contains, _candidate_date)
    baseline_go_live_task = None
    if baseline_plan is not None:
        baseline_go_live_task = _named_go_live_task(
            baseline_plan.tasks, as_of, _contains, _candidate_date
        )
    if baseline_plan is not None:
        baseline_go_live = parse_date(
            None if baseline_go_live_task is None else (
                baseline_go_live_task.baseline_finish or baseline_go_live_task.scheduled_finish
            )
        )
    else:
        baseline_finish = None if go_live_task is None else go_live_task.baseline_finish
        baseline_go_live = parse_date(baseline_finish)
    current_finish = None if go_live_task is None else go_live_task.scheduled_finish
    current_go_live = parse_date(current_finish)

    gross = None
    holiday_count = None
    net = None
    if baseline_go_live is None or current_go_live is None:
        gross = None
        holiday_count = None
        net = None
    elif current_go_live > baseline_go_live:
        gross = _weekdays_after(baseline_go_live, current_go_live)
        if calendar_source == "project":
            holiday_count = _holiday_weekdays_after(baseline_go_live, current_go_live, holidays)
            net = max(0, gross - holiday_count)
        else:
            holiday_count = None
            net = gross
    else:
        gross = 0
        holiday_count = 0 if calendar_source == "project" else None
        net = 0

    phase_tasks = select_phase_summaries(current_plan.tasks, project_name=current_plan.name)
    go_live_id = None if go_live_task is None else go_live_task.id
    successors = _successor_map(current_plan.tasks)
    has_links = any(task.predecessor_ids for task in current_plan.tasks)
    by_id = {task.id: task for task in current_plan.tasks}
    baseline_index = _baseline_index(
        baseline_plan.tasks if baseline_plan is not None else current_plan.tasks,
        from_embedded_baseline=baseline_plan is None,
        parse_date=parse_date,
    )

    task_order = {task.id: index for index, task in enumerate(current_plan.tasks)}
    candidates: list[tuple[PlanTaskData, str, set[date], PlanTaskData | None, str]] = []
    matching_unresolved = False
    if net and net > 0:
        for task in current_plan.tasks:
            if task.is_summary or task.id == go_live_id:
                continue
            if _is_go_live_task(task, _contains):
                continue
            matched, source = match_task(task, baseline_index)
            if source == "ambiguous":
                matching_unresolved = True
                continue
            task_type = _classify_task_type(task, matched, parse_date)
            if task_type is None:
                continue
            named = _named_mapping_type(task.name) is not None
            on_path = go_live_id is not None and _reaches_task(
                successors, task.id, go_live_id
            )
            if has_links and not named and not on_path:
                continue
            impact = _impact_working_days(task, matched, task_type, holidays, parse_date)
            if not named and baseline_go_live and current_go_live:
                window = _working_day_set(
                    baseline_go_live,
                    current_go_live,
                    holidays,
                    inclusive_start=False,
                )
                impact &= window
            if not impact:
                continue
            candidates.append((task, task_type, impact, matched, source))

    rows = _attribute_unique_days(
        candidates,
        net=net or 0,
        tasks=current_plan.tasks,
        phases=phase_tasks,
        successors=successors,
        by_id=by_id,
        go_live_task=go_live_task,
        parse_date=parse_date,
    )
    phase_order = {phase.name: index for index, phase in enumerate(phases)}
    rows.sort(
        key=lambda row: (
            phase_order.get(row.parent_name or "", len(phase_order)),
            task_order.get(row.current_task_id or -1, 10**9),
        )
    )
    total = sum(row.shift_days or 0 for row in rows)
    if net is None:
        recon_status = "unavailable"
        warning = None
    elif matching_unresolved:
        recon_status = "requires_validation"
        warning = _RECONCILE_WARNING
    else:
        recon_status = "reconciled"
        warning = None

    return DelayMappingSheet(
        baseline_go_live=None if baseline_go_live is None else baseline_go_live.isoformat(),
        current_go_live=None if current_go_live is None else current_go_live.isoformat(),
        gross_working_day_shift=gross,
        shift_working_days=gross,
        holidays=holiday_count,
        net_working_day_shift=net,
        actual_shift_working_days=net,
        attributed_shift_days=total,
        unattributed_shift_days=0,
        unattributed_status=None,
        delay_shift_days=sum(
            row.shift_days or 0 for row in rows if row.task_type == "delay"
        ),
        additional_shift_days=sum(
            row.shift_days or 0 for row in rows if row.task_type == "additional"
        ),
        total_delayed_days=total,
        delayed_task_count=sum(1 for row in rows if row.task_type == "delay"),
        reconciliation_status=recon_status,
        reconciliation_warning=warning,
        calendar_source=calendar_source,
        matching_requires_validation=matching_unresolved,
        phase_attribution=[],
        owner_attribution=[],
        type_attribution=[],
        rows=rows,
    )


def match_task(
    current: PlanTaskData,
    baseline_index: dict[str, object],
) -> tuple[PlanTaskData | None, str]:
    """Match a current task to a baseline task. Never guess when the match is ambiguous."""

    by_id: dict[int, PlanTaskData] = baseline_index["by_id"]  # type: ignore[assignment]
    by_wbs: dict[str, list[PlanTaskData]] = baseline_index["by_wbs"]  # type: ignore[assignment]
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_hierarchy"]  # type: ignore[assignment]
    by_name_phase: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_name_phase"]  # type: ignore[assignment]

    hit = by_id.get(current.id)
    if hit is not None:
        return hit, "id"
    wbs = (current.wbs or "").strip()
    if wbs:
        wbs_hits = by_wbs.get(wbs, [])
        if len(wbs_hits) == 1:
            return wbs_hits[0], "wbs"
        if len(wbs_hits) > 1:
            return None, "ambiguous"
    parent = (current.wbs or "").rsplit(".", 1)[0] if (current.wbs or "").count(".") else ""
    hierarchy_key = (_norm(current.name), _norm(parent))
    hier_hits = by_hierarchy.get(hierarchy_key, [])
    if len(hier_hits) == 1:
        return hier_hits[0], "hierarchy"
    if len(hier_hits) > 1:
        return None, "ambiguous"
    name_key = (_norm(current.name), str(current.outline_level))
    name_hits = by_name_phase.get(name_key, [])
    if len(name_hits) == 1:
        return name_hits[0], "name_phase"
    if len(name_hits) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _baseline_index(
    tasks: list[PlanTaskData],
    *,
    from_embedded_baseline: bool,
    parse_date,
) -> dict[str, object]:
    scoped = []
    for task in tasks:
        if task.is_summary:
            continue
        if from_embedded_baseline and not _in_baseline(task, parse_date):
            continue
        scoped.append(task)
    by_id = {task.id: task for task in scoped}
    by_wbs: dict[str, list[PlanTaskData]] = {}
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = {}
    by_name_phase: dict[tuple[str, str], list[PlanTaskData]] = {}
    for task in scoped:
        wbs = (task.wbs or "").strip()
        if wbs:
            by_wbs.setdefault(wbs, []).append(task)
        parent = wbs.rsplit(".", 1)[0] if wbs.count(".") else ""
        by_hierarchy.setdefault((_norm(task.name), _norm(parent)), []).append(task)
        by_name_phase.setdefault((_norm(task.name), str(task.outline_level)), []).append(task)
    return {
        "by_id": by_id,
        "by_wbs": by_wbs,
        "by_hierarchy": by_hierarchy,
        "by_name_phase": by_name_phase,
    }


def _in_baseline(task: PlanTaskData, parse_date) -> bool:
    return bool(
        task.comparison_available
        or parse_date(task.baseline_start)
        or parse_date(task.baseline_finish)
    )


def _classify_task_type(
    current: PlanTaskData,
    baseline: PlanTaskData | None,
    parse_date,
) -> str | None:
    named = _named_mapping_type(current.name)
    if named:
        return named
    if _explicit_additional(current) or baseline is None:
        return "additional"
    return None


def _named_mapping_type(name: str | None) -> str | None:
    text = name or ""
    if _DELAY_WORD.search(text):
        return "delay"
    if _ADDITIONAL_WORD.search(text):
        return "additional"
    return None


def _explicit_additional(task: PlanTaskData) -> bool:
    gate = (task.gate or "").strip().casefold()
    return gate in _EXPLICIT_ADDITIONAL


def _impact_working_days(
    current: PlanTaskData,
    baseline: PlanTaskData | None,
    task_type: str,
    holidays: set[date],
    parse_date,
) -> set[date]:
    current_finish = parse_date(current.scheduled_finish)
    current_start = parse_date(current.scheduled_start)
    if task_type == "delay" and baseline is not None:
        baseline_finish = parse_date(baseline.baseline_finish or baseline.scheduled_finish)
        if baseline_finish and current_finish and current_finish > baseline_finish:
            return _working_day_set(
                baseline_finish, current_finish, holidays, inclusive_start=False
            )
        baseline_start = parse_date(baseline.baseline_start or baseline.scheduled_start)
        if baseline_start and current_start and current_start > baseline_start:
            return _working_day_set(
                baseline_start, current_start, holidays, inclusive_start=False
            )
    start = current_start or (
        parse_date(None if baseline is None else baseline.baseline_start)
    )
    finish = current_finish or (
        parse_date(None if baseline is None else baseline.baseline_finish)
    )
    if start and finish and finish >= start:
        return _working_day_set(start, finish, holidays, inclusive_start=True)
    return set()


def _attribute_unique_days(
    candidates: list[tuple[PlanTaskData, str, set[date], PlanTaskData | None, str]],
    *,
    net: int,
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
    parse_date,
) -> list[DelayMappingRow]:
    if net <= 0 or not candidates:
        return []
    ordered = sorted(
        candidates,
        key=lambda item: (
            min(item[2]) if item[2] else date.max,
            item[0].wbs or "",
            item[0].id,
        ),
    )
    claimed: set[date] = set()
    remaining = net
    rows: list[DelayMappingRow] = []
    for task, task_type, impact, matched, source in ordered:
        if remaining <= 0:
            break
        unique = sorted(day for day in impact if day not in claimed)
        take = unique[:remaining]
        if not take:
            continue
        claimed.update(take)
        remaining -= len(take)
        rows.append(
            _register_row(
                tasks,
                phases,
                task,
                matched,
                task_type,
                shift_days=len(take),
                successors=successors,
                by_id=by_id,
                go_live_task=go_live_task,
                parse_date=parse_date,
                calculation_source=source,
            )
        )
    return rows


def _register_row(
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    task: PlanTaskData,
    baseline: PlanTaskData | None,
    task_type: str,
    *,
    shift_days: int,
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
    parse_date,
    calculation_source: str,
) -> DelayMappingRow:
    if baseline is None:
        planned_start = None
        planned_finish = None
    else:
        planned_start = parse_date(baseline.baseline_start or baseline.scheduled_start)
        planned_finish = parse_date(baseline.baseline_finish or baseline.scheduled_finish)
    if baseline is not None and baseline.baseline_start:
        planned_start = parse_date(baseline.baseline_start)
    if baseline is not None and baseline.baseline_finish:
        planned_finish = parse_date(baseline.baseline_finish)
    current_start = parse_date(task.scheduled_start)
    current_finish = parse_date(task.scheduled_finish)
    names = _resolved_owner_names(task, tasks)
    successor_ids = list(successors.get(task.id, []))
    successor_names, milestone_names = _impacted_names(task.id, successors, by_id, go_live_task)
    parent = _containing_phase(tasks, phases, task)
    on_path = go_live_task is not None and _reaches_task(successors, task.id, go_live_task.id)
    calc = (
        "baseline_finish_to_current_finish"
        if task_type == "delay"
        else "additional_incremental"
    )
    return DelayMappingRow(
        name=task.name,
        parent_name=None if parent is None else parent.name,
        wbs=(task.wbs or "").strip() or None,
        task_type=task_type,
        shift_days=shift_days,
        delay_days=shift_days,
        owner=" & ".join(names) if names else None,
        owner_class=_owner_class(names),
        planned_start=None if planned_start is None else planned_start.isoformat(),
        planned_finish=None if planned_finish is None else planned_finish.isoformat(),
        revised_start=None if current_start is None else current_start.isoformat(),
        revised_finish=None if current_finish is None else current_finish.isoformat(),
        primary_reason=None,
        go_live_impact="high" if on_path else None,
        mitigation_plan=None,
        impacted_successors=successor_names,
        impacted_milestones=milestone_names,
        baseline_task_id=None if baseline is None else baseline.id,
        current_task_id=task.id,
        outline_number=(task.wbs or "").strip() or None,
        predecessor_ids=list(task.predecessor_ids),
        successor_ids=successor_ids,
        go_live_path_impact=on_path,
        calculation_source=f"{calc}:{calculation_source}",
    )


def _owner_names(task: PlanTaskData) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in task.assignments:
        name = (item.resource_name or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _resolved_owner_names(task: PlanTaskData, tasks: list[PlanTaskData]) -> list[str]:
    names = _owner_names(task)
    if names:
        return names
    wbs = (task.wbs or "").strip()
    while "." in wbs:
        wbs = wbs.rsplit(".", 1)[0]
        parent = next((item for item in tasks if (item.wbs or "").strip() == wbs), None)
        if parent is None:
            continue
        names = _owner_names(parent)
        if names:
            return names
    return []


def _owner_class(names: list[str]) -> str:
    if not names:
        return "unknown"
    client_m = client_owner_markers()
    internal_m = internal_owner_markers()
    kinds: set[str] = set()
    for name in names:
        low = name.casefold()
        is_client = any(marker in low for marker in client_m)
        is_internal = any(marker in low for marker in internal_m)
        if is_client and is_internal:
            kinds.add("shared")
        elif is_client:
            kinds.add("client")
        elif is_internal:
            kinds.add("internal")
        else:
            kinds.add("unknown")
    if "shared" in kinds or {"client", "internal"} <= kinds:
        return "shared"
    if "client" in kinds and "internal" not in kinds:
        return "client"
    if "internal" in kinds and "client" not in kinds:
        return "internal"
    return "unknown"


def _impacted_names(
    task_id: int,
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
) -> tuple[list[str], list[str]]:
    seen: set[int] = set()
    queue = list(successors.get(task_id, []))
    successor_names: list[str] = []
    milestone_names: list[str] = []
    while queue:
        nxt = queue.pop(0)
        if nxt in seen:
            continue
        seen.add(nxt)
        item = by_id.get(nxt)
        if item is None or item.is_summary:
            queue.extend(successors.get(nxt, []))
            continue
        if item.name not in successor_names:
            successor_names.append(item.name)
        if item.is_milestone or (go_live_task is not None and item.id == go_live_task.id):
            if item.name not in milestone_names:
                milestone_names.append(item.name)
        queue.extend(successors.get(nxt, []))
        if len(successor_names) >= 12:
            break
    if go_live_task is not None and go_live_task.name not in milestone_names:
        if _reaches_task(successors, task_id, go_live_task.id):
            milestone_names.append(go_live_task.name)
    return successor_names[:8], milestone_names[:6]


def _containing_phase(
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    task: PlanTaskData,
) -> PlanTaskData | None:
    from app.wsr.facts import _is_under

    matches = [
        phase for phase in phases if phase.id == task.id or _is_under(tasks, phase, task)
    ]
    if matches:
        return max(matches, key=lambda item: (item.outline_level, len((item.wbs or "").strip())))
    wbs = (task.wbs or "").strip()
    if not wbs:
        return None
    wbs_matches = []
    for phase in phases:
        prefix = (phase.wbs or "").strip()
        if prefix and (wbs == prefix or wbs.startswith(prefix + ".")):
            wbs_matches.append(phase)
    if not wbs_matches:
        return None
    return max(wbs_matches, key=lambda item: len((item.wbs or "").strip()))


def _is_go_live_task(task: PlanTaskData, contains) -> bool:
    gate = (task.gate or "").strip().casefold()
    if gate in _EXPLICIT_GO_LIVE:
        return True
    return contains(task.gate, go_live_markers()) or contains(task.name, go_live_markers())


def _named_go_live_task(
    tasks: list[PlanTaskData],
    as_of: date,
    contains,
    candidate_date,
) -> PlanTaskData | None:
    explicit = [task for task in tasks if (task.gate or "").strip().casefold() in _EXPLICIT_GO_LIVE]
    named = explicit or [task for task in tasks if _is_go_live_task(task, contains)]
    if not named:
        return None
    dated = [(task, when) for task in named if (when := candidate_date(task)) is not None]
    if not dated:
        return named[0]
    future = [(task, when) for task, when in dated if when >= as_of]
    if future:
        return min(future, key=lambda item: item[1])[0]
    return max(dated, key=lambda item: item[1])[0]


def _successor_map(tasks: list[PlanTaskData]) -> dict[int, list[int]]:
    successors: dict[int, list[int]] = {}
    for task in tasks:
        for pred in task.predecessor_ids:
            successors.setdefault(pred, []).append(task.id)
    return successors


def _reaches_task(successors: dict[int, list[int]], start: int, target: int) -> bool:
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


def _holiday_set(plan: ProjectPlanData, parse_date) -> set[date]:
    days: set[date] = set()
    for raw in plan.holiday_dates:
        parsed = parse_date(raw)
        if parsed is not None:
            days.add(parsed)
    return days


def _weekdays_after(start: date, end: date) -> int:
    return len(
        _working_day_set(
            start,
            end,
            holidays=set(),
            inclusive_start=False,
            skip_holidays=False,
        )
    )


def _holiday_weekdays_after(start: date, end: date, holidays: set[date]) -> int:
    count = 0
    cursor = start + timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5 and cursor in holidays:
            count += 1
        cursor += timedelta(days=1)
    return count


def _working_day_set(
    start: date,
    end: date,
    holidays: set[date],
    *,
    inclusive_start: bool,
    skip_holidays: bool = True,
) -> set[date]:
    if end < start:
        return set()
    cursor = start if inclusive_start else start + timedelta(days=1)
    days: set[date] = set()
    while cursor <= end:
        if cursor.weekday() < 5 and not (skip_holidays and cursor in holidays):
            days.add(cursor)
        cursor += timedelta(days=1)
    return days


def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().split())

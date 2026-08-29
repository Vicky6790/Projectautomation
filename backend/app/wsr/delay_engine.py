"""Schedule variance and Go-Live delay attribution. Dates and days are never invented."""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.models import (
    DelayAttributionBucket,
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

_DELAY_WORD = re.compile(r"\bdelay\b", re.I)
_ADDITIONAL_WORD = re.compile(r"\badditional\b", re.I)


def build_delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,
) -> DelayMappingSheet:
    from app.wsr.facts import (
        _candidate_date,
        _contains,
        parse_date,
        select_phase_summaries,
    )

    holidays = _holiday_set(plan, parse_date)
    go_live_task = _named_go_live_task(plan.tasks, as_of, _contains, _candidate_date)
    baseline_go_live = parse_date(None if go_live_task is None else go_live_task.baseline_finish)
    current_go_live = go_live_date or parse_date(
        None if go_live_task is None else go_live_task.scheduled_finish
    )
    gross = None
    holiday_count = None
    net = None
    if baseline_go_live and current_go_live and current_go_live > baseline_go_live:
        gross = _weekdays_after(baseline_go_live, current_go_live)
        if plan.calendar_available or plan.holiday_dates:
            holiday_count = _holiday_weekdays_after(baseline_go_live, current_go_live, holidays)
            net = gross - holiday_count
        else:
            net = gross
    elif baseline_go_live and current_go_live:
        gross = 0
        holiday_count = 0 if (plan.calendar_available or plan.holiday_dates) else None
        net = 0

    phase_tasks = select_phase_summaries(plan.tasks, project_name=plan.name)
    go_live_id = None if go_live_task is None else go_live_task.id
    successors = _successor_map(plan.tasks)
    has_links = any(task.predecessor_ids for task in plan.tasks)
    by_id = {task.id: task for task in plan.tasks}

    candidates: list[tuple[PlanTaskData, str, set[date]]] = []
    if net and net > 0 and go_live_id is not None:
        for task in plan.tasks:
            if task.is_summary or task.id == go_live_id:
                continue
            if _contains(task.name, go_live_markers()) or _contains(task.gate, go_live_markers()):
                continue
            task_type = _classify_task_type(task, parse_date)
            if task_type is None:
                continue
            on_path = _reaches_task(successors, task.id, go_live_id)
            named = _named_mapping_type(task.name) is not None
            if has_links:
                if not on_path:
                    continue
            elif not named:
                continue
            impact = _impact_working_days(task, task_type, holidays, parse_date)
            if not impact:
                continue
            candidates.append((task, task_type, impact))

    attributed_rows = _attribute_unique_days(
        candidates,
        net=net or 0,
        tasks=plan.tasks,
        phases=phase_tasks,
        successors=successors,
        by_id=by_id,
        go_live_task=go_live_task,
        parse_date=parse_date,
    )
    phase_order = {phase.name: index for index, phase in enumerate(phases)}
    attributed_rows.sort(
        key=lambda row: (
            phase_order.get(row.parent_name or "", len(phase_order)),
            row.parent_name or "",
            -(row.shift_days or 0),
            row.name,
        )
    )
    attributed = sum(row.shift_days or 0 for row in attributed_rows)
    unattributed = 0 if net is None else max(0, net - attributed)
    status = None
    if net is not None:
        status = "requires_pm_validation" if unattributed else "explained"
    delay_days = sum(row.shift_days or 0 for row in attributed_rows if row.task_type == "delay")
    additional_days = sum(
        row.shift_days or 0 for row in attributed_rows if row.task_type == "additional"
    )
    return DelayMappingSheet(
        baseline_go_live=None if baseline_go_live is None else baseline_go_live.isoformat(),
        current_go_live=None if current_go_live is None else current_go_live.isoformat(),
        gross_working_day_shift=gross,
        shift_working_days=gross,
        holidays=holiday_count,
        net_working_day_shift=net,
        actual_shift_working_days=net,
        attributed_shift_days=attributed,
        unattributed_shift_days=unattributed,
        unattributed_status=status,
        delay_shift_days=delay_days,
        additional_shift_days=additional_days,
        total_delayed_days=attributed,
        delayed_task_count=sum(1 for row in attributed_rows if row.task_type == "delay"),
        phase_attribution=_phase_buckets(attributed_rows, phases),
        owner_attribution=_owner_buckets(attributed_rows),
        type_attribution=_type_buckets(delay_days, additional_days, attributed_rows),
        rows=attributed_rows,
    )


def _classify_task_type(task: PlanTaskData, parse_date) -> str | None:
    named = _named_mapping_type(task.name)
    if named:
        return named
    planned_start = parse_date(task.baseline_start)
    planned_finish = parse_date(task.baseline_finish)
    current_start = parse_date(task.scheduled_start)
    current_finish = parse_date(task.scheduled_finish)
    has_baseline = planned_start is not None or planned_finish is not None
    has_current = current_start is not None or current_finish is not None
    if not has_baseline and has_current:
        return "additional"
    if planned_finish and current_finish and current_finish > planned_finish:
        return "delay"
    return None


def _named_mapping_type(name: str | None) -> str | None:
    text = name or ""
    if _DELAY_WORD.search(text):
        return "delay"
    if _ADDITIONAL_WORD.search(text):
        return "additional"
    return None


def _impact_working_days(task: PlanTaskData, task_type: str, holidays: set[date], parse_date) -> set[date]:
    planned_finish = parse_date(task.baseline_finish)
    current_finish = parse_date(task.scheduled_finish)
    planned_start = parse_date(task.baseline_start)
    current_start = parse_date(task.scheduled_start)
    if task_type == "delay" and planned_finish and current_finish and current_finish > planned_finish:
        return _working_day_set(planned_finish, current_finish, holidays, inclusive_start=False)
    start = current_start or planned_start
    finish = current_finish or planned_finish
    if start and finish and finish >= start:
        return _working_day_set(start, finish, holidays, inclusive_start=True)
    return set()


def _attribute_unique_days(
    candidates: list[tuple[PlanTaskData, str, set[date]]],
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
            item[0].name,
        ),
    )
    claimed: set[date] = set()
    remaining = net
    rows: list[DelayMappingRow] = []
    for task, task_type, impact in ordered:
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
                task_type,
                shift_days=len(take),
                successors=successors,
                by_id=by_id,
                go_live_task=go_live_task,
                parse_date=parse_date,
            )
        )
    return rows


def _register_row(
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    task: PlanTaskData,
    task_type: str,
    *,
    shift_days: int,
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
    parse_date,
) -> DelayMappingRow:
    planned_start = parse_date(task.baseline_start)
    planned_finish = parse_date(task.baseline_finish)
    current_start = parse_date(task.scheduled_start)
    current_finish = parse_date(task.scheduled_finish)
    names = _owner_names(task)
    successor_names, milestone_names = _impacted_names(
        task.id, successors, by_id, go_live_task
    )
    parent = _containing_phase(tasks, phases, task)
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
        go_live_impact="high",
        mitigation_plan=None,
        impacted_successors=successor_names,
        impacted_milestones=milestone_names,
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


def _phase_buckets(rows: list[DelayMappingRow], phases: list[PhaseStatus]) -> list[DelayAttributionBucket]:
    totals: dict[str, list[int]] = {}
    for row in rows:
        key = row.parent_name or "Other"
        slot = totals.setdefault(key, [0, 0])
        slot[0] += row.shift_days or 0
        slot[1] += 1
    order = [phase.name for phase in phases]
    keys = [name for name in order if name in totals] + [key for key in totals if key not in order]
    return [
        DelayAttributionBucket(key=key, label=key, shift_days=totals[key][0], task_count=totals[key][1])
        for key in keys
        if totals[key][0]
    ]


def _owner_buckets(rows: list[DelayMappingRow]) -> list[DelayAttributionBucket]:
    labels = {
        "internal": "Internal",
        "client": "Client",
        "shared": "Shared",
        "unknown": "Unknown",
    }
    totals: dict[str, list[int]] = {}
    for row in rows:
        key = row.owner_class
        slot = totals.setdefault(key, [0, 0])
        slot[0] += row.shift_days or 0
        slot[1] += 1
    return [
        DelayAttributionBucket(key=key, label=labels[key], shift_days=days[0], task_count=days[1])
        for key, days in totals.items()
        if days[0]
    ]


def _type_buckets(
    delay_days: int,
    additional_days: int,
    rows: list[DelayMappingRow],
) -> list[DelayAttributionBucket]:
    delay_count = sum(1 for row in rows if row.task_type == "delay")
    additional_count = sum(1 for row in rows if row.task_type == "additional")
    buckets: list[DelayAttributionBucket] = []
    if delay_days:
        buckets.append(
            DelayAttributionBucket(
                key="delay",
                label="DELAY",
                shift_days=delay_days,
                task_count=delay_count,
            )
        )
    if additional_days:
        buckets.append(
            DelayAttributionBucket(
                key="additional",
                label="ADDITIONAL",
                shift_days=additional_days,
                task_count=additional_count,
            )
        )
    return buckets


def _containing_phase(
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    task: PlanTaskData,
) -> PlanTaskData | None:
    from app.wsr.facts import _is_under

    matches = [
        phase for phase in phases if phase.id == task.id or _is_under(tasks, phase, task)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item.outline_level)


def _named_go_live_task(tasks: list[PlanTaskData], as_of: date, contains, candidate_date) -> PlanTaskData | None:
    named = [
        task
        for task in tasks
        if contains(task.gate, go_live_markers()) or contains(task.name, go_live_markers())
    ]
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
    return len(_working_day_set(start, end, holidays=set(), inclusive_start=False, skip_holidays=False))


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

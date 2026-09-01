"""Deterministic Delay Mapping from one MPP. Numbers come from dates, calendars, and links — never AI."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import (
    DelayMappingRow,
    DelayMappingSheet,
    PhaseStatus,
    PlanTaskData,
    ProjectPlanData,
)
from app.wsr.detection import client_owner_markers, internal_owner_markers

_INCOMPLETE_MESSAGE = (
    "Unable to determine deadline impact because required "
    "MPP schedule/dependency information is incomplete."
)
_CONFIGURED_GO_LIVE = frozenset({"go_live", "go-live", "go live", "golive"})
_RECOGNIZED_GO_LIVE = frozenset(
    {
        "go live",
        "project go live",
        "go live date",
        "production go live",
    }
)
_BLANK_BASELINE = frozenset({"", "n/a", "na", "null", "none", "unavailable", "-"})
_ADDITIONAL_REASON = "Additional task contributes to the dependency chain ending at Go-Live."


def build_delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,
    baseline_plan: ProjectPlanData | None = None,
) -> DelayMappingSheet:
    from app.wsr.facts import _candidate_date, parse_date, select_phase_summaries

    _ = go_live_date
    _ = baseline_plan
    holidays = _holiday_set(plan, parse_date)
    calendar_source = (
        "project" if (plan.calendar_available or plan.holiday_dates) else "weekdays_fallback"
    )
    graph_error = _graph_validation_error(plan.tasks)
    go_live_task, go_live_status = _select_go_live(plan.tasks, as_of, _candidate_date, parse_date)
    if graph_error or go_live_status in {"ambiguous", "unavailable"}:
        status = "ambiguous" if go_live_status == "ambiguous" else "unavailable"
        return _failed_sheet(
            go_live_task=None if go_live_status != "calculated" else go_live_task,
            go_live_status=status,
            calendar_source=calendar_source,
            parse_date=parse_date,
        )

    baseline_go_live = parse_date(None if go_live_task is None else go_live_task.baseline_finish)
    current_go_live = _task_finish(go_live_task, parse_date)
    if go_live_task is None or current_go_live is None or baseline_go_live is None:
        return _failed_sheet(
            go_live_task=go_live_task,
            go_live_status="unavailable",
            calendar_source=calendar_source,
            parse_date=parse_date,
        )
    go_live_status = "calculated"

    gross = 0
    holiday_count = 0 if calendar_source == "project" else None
    net = 0
    if current_go_live > baseline_go_live:
        gross = _weekdays_after(baseline_go_live, current_go_live)
        if calendar_source == "project":
            holiday_count = _holiday_weekdays_after(baseline_go_live, current_go_live, holidays)
            net = max(0, gross - holiday_count)
        else:
            net = gross

    phase_tasks = select_phase_summaries(plan.tasks, project_name=plan.name)
    go_live_id = go_live_task.id
    successors = _successor_map(plan.tasks)
    by_id = {task.id: task for task in plan.tasks}
    wbs_index = {(task.wbs or "").strip(): task for task in plan.tasks if (task.wbs or "").strip()}
    driving_ids = _driving_path_ids(go_live_task, plan.tasks, successors)

    classified: list[dict] = []
    unchanged_count = 0
    ahead_count = 0
    non_impacting_additional = 0
    for task in _relevant_leaves(plan.tasks):
        if task.id == go_live_id:
            continue
        current_finish = _task_finish(task, parse_date)
        current_start = _task_start(task, parse_date)
        baseline_finish = _baseline_finish(task, parse_date)
        if baseline_finish is None:
            classified.append(
                {
                    "task": task,
                    "task_type": "additional",
                    "baseline_finish": None,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": None,
                    "evidence": _ADDITIONAL_REASON,
                }
            )
            continue
        if current_finish is None:
            continue
        if current_finish > baseline_finish:
            shift = len(
                _working_day_set(baseline_finish, current_finish, holidays, inclusive_start=False)
            )
            classified.append(
                {
                    "task": task,
                    "task_type": "delay",
                    "baseline_finish": baseline_finish,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": shift,
                    "evidence": (
                        "Current Finish is later than Baseline Finish. "
                        f"Working-day variance: {shift}."
                    ),
                }
            )
        elif current_finish < baseline_finish:
            ahead_count += 1
        else:
            unchanged_count += 1

    report_items = [item for item in classified if item["task_type"] in {"delay", "additional"}]
    for item in report_items:
        item["potential_impact"] = _potential_go_live_impact(
            item,
            driving_ids=driving_ids,
            successors=successors,
            go_live_id=go_live_id,
            net=net,
            holidays=holidays,
        )
    _attribute_go_live_impact(report_items, net=net or 0)
    visible: list[dict] = []
    for item in report_items:
        impact = int(item.get("go_live_impact_days") or 0)
        if impact <= 0:
            if item["task_type"] == "additional":
                non_impacting_additional += 1
            continue
        if item["task_type"] == "additional":
            item["evidence"] = _ADDITIONAL_REASON
        else:
            item["evidence"] = (
                f"{item['evidence']} Delayed task contributes to the dependency chain ending at Go-Live."
            )
        visible.append(item)

    rows: list[DelayMappingRow] = []
    for item in visible:
        rows.append(
            _register_row(
                plan.tasks,
                phase_tasks,
                wbs_index,
                item["task"],
                item["task_type"],
                shift_days=item.get("shift_days") if item["task_type"] == "delay" else None,
                go_live_impact_days=item.get("go_live_impact_days") or 0,
                successors=successors,
                by_id=by_id,
                go_live_task=go_live_task,
                driving_ids=driving_ids,
                parse_date=parse_date,
                evidence_reason=item["evidence"],
            )
        )
    rows.sort(
        key=lambda row: (
            row.revised_start or row.revised_finish or "9999-12-31",
            row.current_task_id or 10**9,
        )
    )

    delay_count = sum(1 for row in rows if row.task_type == "delay")
    additional_count = sum(1 for row in rows if row.task_type == "additional")
    delay_shift = sum(row.go_live_impact_days or 0 for row in rows if row.task_type == "delay")
    additional_shift = sum(row.go_live_impact_days or 0 for row in rows if row.task_type == "additional")
    attributed = sum(row.go_live_impact_days or 0 for row in rows)
    _ = non_impacting_additional

    return DelayMappingSheet(
        report_status="verified",
        go_live_status=go_live_status,
        baseline_go_live=baseline_go_live.isoformat(),
        current_go_live=current_go_live.isoformat(),
        gross_working_day_shift=gross,
        shift_working_days=gross,
        holidays=holiday_count,
        net_working_day_shift=net,
        actual_shift_working_days=net,
        attributed_shift_days=attributed,
        unattributed_shift_days=max(0, (net or 0) - attributed),
        unattributed_status="explained",
        delay_shift_days=delay_shift,
        additional_shift_days=additional_shift,
        total_delayed_days=attributed,
        delayed_task_count=delay_count,
        additional_task_count=additional_count,
        matched_task_count=sum(1 for item in classified if item["task_type"] != "additional"),
        removed_task_count=0,
        unchanged_task_count=unchanged_count,
        ahead_task_count=ahead_count,
        ambiguous_task_count=0,
        baseline_task_count=len(_relevant_leaves(plan.tasks)),
        current_task_count=len(_relevant_leaves(plan.tasks)),
        reconciliation_status="reconciled",
        reconciliation_warning=None,
        calendar_source=calendar_source,
        matching_requires_validation=False,
        phase_attribution=[],
        owner_attribution=[],
        type_attribution=[],
        rows=rows,
        review_rows=[],
        removed_rows=[],
    )


def _failed_sheet(
    *,
    go_live_task: PlanTaskData | None,
    go_live_status: str,
    calendar_source: str,
    parse_date,
) -> DelayMappingSheet:
    baseline = None if go_live_task is None else parse_date(go_live_task.baseline_finish)
    current = _task_finish(go_live_task, parse_date)
    return DelayMappingSheet(
        report_status="validation_failed" if go_live_status != "ambiguous" else "requires_review",
        go_live_status=go_live_status if go_live_status in {"calculated", "unavailable", "ambiguous"} else "unavailable",
        baseline_go_live=None if baseline is None else baseline.isoformat(),
        current_go_live=None if current is None else current.isoformat(),
        gross_working_day_shift=None,
        shift_working_days=None,
        holidays=None,
        net_working_day_shift=None,
        actual_shift_working_days=None,
        attributed_shift_days=0,
        unattributed_shift_days=0,
        delay_shift_days=0,
        additional_shift_days=0,
        total_delayed_days=0,
        delayed_task_count=0,
        additional_task_count=0,
        reconciliation_status="requires_validation",
        reconciliation_warning=_INCOMPLETE_MESSAGE,
        calendar_source=calendar_source,  # type: ignore[arg-type]
        matching_requires_validation=go_live_status == "ambiguous",
        rows=[],
        review_rows=[],
        removed_rows=[],
    )


def _graph_validation_error(tasks: list[PlanTaskData]) -> str | None:
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        return "duplicate"
    by_id = set(ids)
    for task in tasks:
        for pred in task.predecessor_ids:
            if pred not in by_id:
                return "unresolved"
    if _has_cycle(tasks):
        return "cycle"
    return None


def _has_cycle(tasks: list[PlanTaskData]) -> bool:
    successors = _successor_map(tasks)
    white, gray, black = 0, 1, 2
    color = {task.id: white for task in tasks}

    def visit(nid: int) -> bool:
        color[nid] = gray
        for nxt in successors.get(nid, []):
            if nxt not in color:
                continue
            if color[nxt] == gray:
                return True
            if color[nxt] == white and visit(nxt):
                return True
        color[nid] = black
        return False

    return any(color[nid] == white and visit(nid) for nid in color)


def _relevant_leaves(tasks: list[PlanTaskData]) -> list[PlanTaskData]:
    return [task for task in tasks if not task.is_summary and (task.name or "").strip()]


def _parent_wbs(wbs: str | None) -> str:
    text = (wbs or "").strip()
    if "." not in text:
        return ""
    return text.rsplit(".", 1)[0]


def _canonical_key(task: PlanTaskData, tasks: list[PlanTaskData]) -> str:
    wbs_map = {(item.wbs or "").strip(): item for item in tasks if (item.wbs or "").strip()}
    parent = wbs_map.get(_parent_wbs(task.wbs))
    phase = parent
    while phase is not None and phase.outline_level > 1:
        phase = wbs_map.get(_parent_wbs(phase.wbs))
    return "|".join(
        [
            _norm(None if phase is None else phase.name),
            _norm(None if parent is None else parent.name),
            _norm(task.set_name),
            _norm(task.name),
        ]
    )


def _baseline_finish(task: PlanTaskData, parse_date) -> date | None:
    raw = (task.baseline_finish or "").strip()
    if raw.casefold() in _BLANK_BASELINE:
        return None
    return parse_date(task.baseline_finish)


def _task_finish(task: PlanTaskData | None, parse_date) -> date | None:
    if task is None:
        return None
    return parse_date(task.actual_finish) or parse_date(task.scheduled_finish)


def _task_start(task: PlanTaskData, parse_date) -> date | None:
    return parse_date(task.actual_start) or parse_date(task.scheduled_start)


def _driving_path_ids(
    go_live_task: PlanTaskData | None,
    tasks: list[PlanTaskData],
    successors: dict[int, list[int]],
) -> set[int]:
    """Tasks that drive Go-Live: predecessor chain plus children of summaries on that chain."""
    if go_live_task is None:
        return set()
    wbs_map = {(task.wbs or "").strip(): task for task in tasks if (task.wbs or "").strip()}
    children: dict[int, list[int]] = {}
    for task in tasks:
        parent = wbs_map.get(_parent_wbs(task.wbs))
        if parent is not None:
            children.setdefault(parent.id, []).append(task.id)
    preds: dict[int, list[int]] = {}
    for src, dests in successors.items():
        for dest in dests:
            bucket = preds.setdefault(dest, [])
            if src not in bucket:
                bucket.append(src)
    for task in tasks:
        for pred in task.predecessor_ids:
            bucket = preds.setdefault(task.id, [])
            if pred not in bucket:
                bucket.append(pred)
    on: set[int] = set()
    queue = [go_live_task.id]
    while queue:
        nid = queue.pop()
        if nid in on:
            continue
        on.add(nid)
        for pred in preds.get(nid, []):
            if pred not in on:
                queue.append(pred)
        for child in children.get(nid, []):
            if child not in on:
                queue.append(child)
    return on


def _on_go_live_path(
    task: PlanTaskData,
    *,
    driving_ids: set[int],
    successors: dict[int, list[int]],
    go_live_id: int,
) -> bool:
    if task.id in driving_ids:
        return True
    return _reaches_task(successors, task.id, go_live_id)


def _potential_go_live_impact(
    item: dict,
    *,
    driving_ids: set[int],
    successors: dict[int, list[int]],
    go_live_id: int,
    net: int | None,
    holidays: set[date],
) -> int:
    if net is None or net <= 0:
        return 0
    task: PlanTaskData = item["task"]
    if not _on_go_live_path(task, driving_ids=driving_ids, successors=successors, go_live_id=go_live_id):
        return 0
    slack = task.total_slack_days
    has_float = slack is not None and slack > 0 and task.critical is False
    if has_float:
        return 0
    if item["task_type"] == "delay":
        shift = item["shift_days"] or 0
        if slack is not None and shift and slack >= shift:
            return 0
        return shift
    start = item.get("current_start")
    finish = item.get("current_finish")
    if start and finish and finish >= start:
        return len(_working_day_set(start, finish, holidays, inclusive_start=True))
    return net


def _attribute_go_live_impact(items: list[dict], *, net: int) -> None:
    remaining = max(0, net)
    claimed: set[date] = set()
    ordered = sorted(
        items,
        key=lambda item: (
            item.get("current_start") or item.get("baseline_finish") or date.max,
            0 if item["task_type"] == "delay" else 1,
            item["task"].id,
        ),
    )
    for item in ordered:
        potential = int(item.get("potential_impact") or 0)
        if remaining <= 0 or potential <= 0:
            item["go_live_impact_days"] = 0
            continue
        take = min(potential, remaining)
        finish = item.get("current_finish")
        start = item.get("current_start") or item.get("baseline_finish")
        if start and finish:
            days = sorted(
                day
                for day in _working_day_set(
                    start,
                    finish,
                    set(),
                    inclusive_start=item["task_type"] == "additional",
                )
                if day not in claimed
            )
            if days:
                used = days[:take]
                claimed.update(used)
                take = len(used)
        item["go_live_impact_days"] = take
        remaining -= take


def _register_row(
    tasks: list[PlanTaskData],
    phases: list[PlanTaskData],
    wbs_index: dict[str, PlanTaskData],
    task: PlanTaskData,
    task_type: str,
    *,
    shift_days: int | None,
    go_live_impact_days: int | None,
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
    driving_ids: set[int],
    parse_date,
    evidence_reason: str,
) -> DelayMappingRow:
    _ = wbs_index
    planned_start = parse_date(task.baseline_start)
    planned_finish = _baseline_finish(task, parse_date)
    current_start = _task_start(task, parse_date)
    current_finish = _task_finish(task, parse_date)
    names = _resolved_owner_names(task, tasks)
    successor_ids = list(successors.get(task.id, [])) or list(task.successor_ids)
    successor_names = list(task.successor_names) or _impacted_names(task.id, successors, by_id, go_live_task)[0]
    milestone_names = _impacted_names(task.id, successors, by_id, go_live_task)[1]
    parent = _containing_phase(tasks, phases, task)
    on_path = task.id in driving_ids
    impact_days = go_live_impact_days
    return DelayMappingRow(
        name=task.name,
        parent_name=None if parent is None else parent.name,
        wbs=(task.wbs or "").strip() or None,
        hierarchy_path=_canonical_key(task, tasks),
        task_type=task_type,  # type: ignore[arg-type]
        shift_days=shift_days,
        delay_days=shift_days,
        go_live_impact_days=impact_days,
        owner=" & ".join(names) if names else None,
        owner_class=_owner_class(names),
        planned_start=None if planned_start is None else planned_start.isoformat(),
        planned_finish=None if planned_finish is None else planned_finish.isoformat(),
        revised_start=None if current_start is None else current_start.isoformat(),
        revised_finish=None if current_finish is None else current_finish.isoformat(),
        primary_reason=evidence_reason,
        go_live_impact="high" if (impact_days or 0) > 0 else None,
        mitigation_plan=None,
        impacted_successors=successor_names,
        impacted_milestones=milestone_names,
        predecessor_names=_pred_names(task, by_id),
        successor_names=successor_names,
        baseline_task_id=task.id,
        current_task_id=task.id,
        outline_number=(task.wbs or "").strip() or None,
        predecessor_ids=list(task.predecessor_ids),
        successor_ids=successor_ids,
        go_live_path_impact=on_path and (impact_days or 0) > 0,
        match_status="additional" if task_type == "additional" else "matched",
        calculation_status="calculated",
        evidence_reason=evidence_reason,
        calculation_source="mpp",
    )


def _pred_names(task: PlanTaskData, by_id: dict[int, PlanTaskData]) -> list[str]:
    names = [name.strip() for name in task.predecessor_names if name and name.strip()]
    if names:
        return names
    resolved: list[str] = []
    for pred_id in task.predecessor_ids:
        pred = by_id.get(pred_id)
        resolved.append(pred.name if pred is not None else str(pred_id))
    return resolved


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


def _name_key(value: str | None) -> str:
    return " ".join((value or "").casefold().replace("-", " ").replace("_", " ").split())


def _select_go_live(
    tasks: list[PlanTaskData],
    as_of: date,
    candidate_date,
    parse_date,
) -> tuple[PlanTaskData | None, str]:
    configured = [
        task for task in tasks if (task.gate or "").strip().casefold() in _CONFIGURED_GO_LIVE
    ]
    if configured:
        return _resolve_go_live_candidates(configured, as_of, candidate_date, parse_date)
    recognized = [task for task in tasks if _name_key(task.name) in _RECOGNIZED_GO_LIVE]
    if recognized:
        return _resolve_go_live_candidates(recognized, as_of, candidate_date, parse_date)
    milestones = [task for task in tasks if task.is_milestone and not task.is_summary]
    dated = []
    for task in milestones:
        when = candidate_date(task) or parse_date(task.actual_finish) or parse_date(task.baseline_finish)
        if when is not None:
            dated.append((task, when))
    if not dated:
        return None, "unavailable"
    latest = max(when for _, when in dated)
    at_latest = [task for task, when in dated if when == latest]
    return min(at_latest, key=lambda item: item.id), "calculated"


def _resolve_go_live_candidates(
    named: list[PlanTaskData],
    as_of: date,
    candidate_date,
    parse_date,
) -> tuple[PlanTaskData | None, str]:
    leaves = [task for task in named if not task.is_summary] or named
    milestones = [task for task in leaves if task.is_milestone] or leaves
    dated: list[tuple[PlanTaskData, date]] = []
    for task in milestones:
        when = candidate_date(task) or parse_date(task.actual_finish)
        if when is not None:
            dated.append((task, when))
    finishes = {when for _, when in dated}
    if len(milestones) > 1 and len(finishes) > 1:
        return None, "ambiguous"
    if not dated:
        return milestones[0], "calculated"
    future = [(task, when) for task, when in dated if when >= as_of]
    if future:
        return min(future, key=lambda item: item[1])[0], "calculated"
    return max(dated, key=lambda item: item[1])[0], "calculated"


def _successor_map(tasks: list[PlanTaskData]) -> dict[int, list[int]]:
    successors: dict[int, list[int]] = {}
    for task in tasks:
        for succ_id in task.successor_ids:
            bucket = successors.setdefault(task.id, [])
            if succ_id not in bucket:
                bucket.append(succ_id)
        for pred in task.predecessor_ids:
            bucket = successors.setdefault(pred, [])
            if task.id not in bucket:
                bucket.append(task.id)
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

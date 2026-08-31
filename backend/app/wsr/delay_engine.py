"""Deterministic Delay Mapping. Numbers come from MPP dates, calendars, and links — never AI."""

from __future__ import annotations

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
    "MPP reconciliation failed. Please review the source files before generating the report."
)
_AMBIGUOUS_WARNING = (
    "Delay mapping total does not reconcile with the calculated Go-Live shift. "
    "PM validation required."
)
_EXPLICIT_GO_LIVE = frozenset({"go_live", "go-live", "go live", "golive"})
_VALIDATION_MESSAGE = (
    "MPP reconciliation failed. Please review the source files before generating the report."
)


def build_delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,
    baseline_plan: ProjectPlanData | None = None,
) -> DelayMappingSheet:
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
    go_live_task, go_live_status = _select_go_live(
        current_plan.tasks, as_of, _contains, _candidate_date
    )
    baseline_go_live_task = None
    if baseline_plan is not None:
        baseline_go_live_task, baseline_gl_status = _select_go_live(
            baseline_plan.tasks, as_of, _contains, _candidate_date
        )
        if baseline_gl_status == "ambiguous" or go_live_status == "ambiguous":
            go_live_status = "ambiguous"
    if go_live_status == "ambiguous":
        baseline_go_live = None
        current_go_live = None
    elif baseline_plan is not None:
        baseline_go_live = parse_date(
            None
            if baseline_go_live_task is None
            else (baseline_go_live_task.baseline_finish or baseline_go_live_task.scheduled_finish)
        )
        current_go_live = parse_date(
            None if go_live_task is None else go_live_task.scheduled_finish
        )
        if go_live_task is None:
            go_live_status = "unavailable"
    else:
        baseline_go_live = parse_date(
            None if go_live_task is None else go_live_task.baseline_finish
        )
        current_go_live = parse_date(
            None if go_live_task is None else go_live_task.scheduled_finish
        )
        if go_live_task is None:
            go_live_status = "unavailable"
        elif baseline_go_live is None or current_go_live is None:
            go_live_status = "unavailable"
        else:
            go_live_status = "calculated"

    gross = None
    holiday_count = None
    net = None
    if go_live_status != "calculated" or baseline_go_live is None or current_go_live is None:
        pass
    elif current_go_live > baseline_go_live:
        gross = _weekdays_after(baseline_go_live, current_go_live)
        if calendar_source == "project":
            holiday_count = _holiday_weekdays_after(baseline_go_live, current_go_live, holidays)
            net = max(0, gross - holiday_count)
        else:
            net = gross
    else:
        gross = 0
        holiday_count = 0 if calendar_source == "project" else None
        net = 0

    phase_tasks = select_phase_summaries(current_plan.tasks, project_name=current_plan.name)
    go_live_id = None if go_live_task is None else go_live_task.id
    successors = _successor_map(current_plan.tasks)
    by_id = {task.id: task for task in current_plan.tasks}
    wbs_index = {(task.wbs or "").strip(): task for task in current_plan.tasks if (task.wbs or "").strip()}
    two_file = baseline_plan is not None
    baseline_tasks = baseline_plan.tasks if two_file else current_plan.tasks
    baseline_index = _baseline_index(baseline_tasks, current_plan.tasks, parse_date=parse_date)

    current_leaves = _relevant_leaves(current_plan.tasks)
    baseline_leaves = _relevant_leaves(baseline_tasks)
    matched_baseline_ids: set[int] = set()
    classified: list[dict] = []
    review_rows: list[DelayMappingRow] = []
    matching_unresolved = go_live_status == "ambiguous"

    for task in current_leaves:
        matched, source = match_task(task, baseline_index)
        baseline_finish = parse_date(None if matched is None else matched.baseline_finish)
        current_finish = parse_date(task.actual_finish) or parse_date(task.scheduled_finish)
        current_start = parse_date(task.actual_start) or parse_date(task.scheduled_start)
        if source == "ambiguous":
            matching_unresolved = True
            review_rows.append(
                _register_row(
                    current_plan.tasks,
                    phase_tasks,
                    wbs_index,
                    task,
                    None,
                    "unavailable",
                    shift_days=None,
                    go_live_impact_days=None,
                    successors=successors,
                    by_id=by_id,
                    go_live_task=go_live_task,
                    parse_date=parse_date,
                    match_status="ambiguous",
                    calculation_status="ambiguous_match",
                    evidence_reason="Multiple baseline tasks match this current task. Delay was not calculated.",
                    calculation_source="ambiguous",
                )
            )
            continue
        if matched is None:
            classified.append(
                {
                    "task": task,
                    "matched": None,
                    "task_type": "additional",
                    "source": source,
                    "baseline_finish": None,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": None,
                    "match_status": "additional",
                    "calculation_status": "calculated",
                    "evidence": "Task exists in Current MPP but not in Baseline MPP.",
                }
            )
            continue
        matched_baseline_ids.add(matched.id)
        if go_live_id is not None and task.id == go_live_id:
            continue
        if _is_go_live_task(task, _contains):
            continue
        if baseline_finish is None:
            classified.append(
                {
                    "task": task,
                    "matched": matched,
                    "task_type": "unavailable",
                    "source": source,
                    "baseline_finish": None,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": None,
                    "match_status": "matched",
                    "calculation_status": "baseline_unavailable",
                    "evidence": "Baseline Finish is unavailable. Delay was not calculated.",
                }
            )
            continue
        if current_finish is None:
            classified.append(
                {
                    "task": task,
                    "matched": matched,
                    "task_type": "unavailable",
                    "source": source,
                    "baseline_finish": baseline_finish,
                    "current_finish": None,
                    "current_start": current_start,
                    "shift_days": None,
                    "match_status": "matched",
                    "calculation_status": "baseline_unavailable",
                    "evidence": "Current Finish is unavailable. Delay was not calculated.",
                }
            )
            continue
        if current_finish > baseline_finish:
            shift = len(
                _working_day_set(baseline_finish, current_finish, holidays, inclusive_start=False)
            )
            classified.append(
                {
                    "task": task,
                    "matched": matched,
                    "task_type": "delay",
                    "source": source,
                    "baseline_finish": baseline_finish,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": shift,
                    "match_status": "matched",
                    "calculation_status": "calculated",
                    "evidence": (
                        "Current Finish is later than Baseline Finish. "
                        f"Working-day variance: {shift}."
                    ),
                }
            )
        elif current_finish < baseline_finish:
            classified.append(
                {
                    "task": task,
                    "matched": matched,
                    "task_type": "ahead",
                    "source": source,
                    "baseline_finish": baseline_finish,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": None,
                    "match_status": "matched",
                    "calculation_status": "calculated",
                    "evidence": "Current Finish is earlier than Baseline Finish.",
                }
            )
        else:
            classified.append(
                {
                    "task": task,
                    "matched": matched,
                    "task_type": "unchanged",
                    "source": source,
                    "baseline_finish": baseline_finish,
                    "current_finish": current_finish,
                    "current_start": current_start,
                    "shift_days": 0,
                    "match_status": "matched",
                    "calculation_status": "calculated",
                    "evidence": "Current Finish equals Baseline Finish.",
                }
            )

    removed_rows: list[DelayMappingRow] = []
    if two_file:
        for task in baseline_leaves:
            if task.id in matched_baseline_ids:
                continue
            if _is_go_live_task(task, _contains):
                continue
            removed_rows.append(
                _register_row(
                    current_plan.tasks,
                    phase_tasks,
                    wbs_index,
                    task,
                    task,
                    "removed",
                    shift_days=None,
                    go_live_impact_days=None,
                    successors=successors,
                    by_id=by_id,
                    go_live_task=go_live_task,
                    parse_date=parse_date,
                    match_status="removed",
                    calculation_status="calculated",
                    evidence_reason="Task exists in Baseline MPP but not in Current MPP.",
                    calculation_source="removed",
                )
            )

    report_items = [
        item for item in classified if item["task_type"] in {"delay", "additional"}
    ]
    for item in report_items:
        item["potential_impact"] = _potential_go_live_impact(
            item,
            successors=successors,
            go_live_task=go_live_task,
            net=net,
            holidays=holidays,
            parse_date=parse_date,
        )
    _attribute_go_live_impact(report_items, net=net or 0)

    calc_status_go_live = (
        "go_live_ambiguous"
        if go_live_status == "ambiguous"
        else "go_live_unavailable"
        if go_live_status == "unavailable"
        else "calendar_unavailable"
        if calendar_source == "weekdays_fallback"
        else "calculated"
    )
    rows: list[DelayMappingRow] = []
    for item in report_items:
        status = item["calculation_status"]
        if calc_status_go_live != "calculated" and item["task_type"] == "delay":
            status = calc_status_go_live if item.get("go_live_impact_days") else status
        rows.append(
            _register_row(
                current_plan.tasks,
                phase_tasks,
                wbs_index,
                item["task"],
                item["matched"],
                item["task_type"],
                shift_days=item["shift_days"],
                go_live_impact_days=item.get("go_live_impact_days") or 0,
                successors=successors,
                by_id=by_id,
                go_live_task=go_live_task,
                parse_date=parse_date,
                match_status=item["match_status"],
                calculation_status=status,
                evidence_reason=item["evidence"],
                calculation_source=item["source"],
            )
        )

    rows.sort(
        key=lambda row: (
            row.revised_finish or row.planned_finish or "9999-12-31",
            row.current_task_id or 10**9,
        )
    )

    delay_count = sum(1 for row in rows if row.task_type == "delay")
    additional_count = sum(1 for row in rows if row.task_type == "additional")
    delay_shift = sum(row.shift_days or 0 for row in rows if row.task_type == "delay")
    attributed = sum(row.go_live_impact_days or 0 for row in rows)
    matched_count = sum(
        1
        for item in classified
        if item["match_status"] == "matched"
    ) + (1 if go_live_task is not None and go_live_id is not None else 0)
    unchanged_count = sum(1 for item in classified if item["task_type"] == "unchanged")
    ahead_count = sum(1 for item in classified if item["task_type"] == "ahead")

    current_count = len(current_leaves)
    baseline_count = len(baseline_leaves)
    additional_classified = sum(1 for item in classified if item["task_type"] == "additional")
    ambiguous_count = len(review_rows)
    removed_count = len(removed_rows)
    current_accounted = matched_count + additional_classified + ambiguous_count
    # Go-live was skipped in classified but counted in matched_count when present.
    classified_non_gl = len(classified)
    current_accounted = classified_non_gl + ambiguous_count + (
        1 if go_live_task is not None else 0
    )
    baseline_accounted = len(matched_baseline_ids) + removed_count
    if two_file:
        recon_ok = current_accounted == current_count and baseline_accounted == baseline_count
    else:
        recon_ok = current_accounted == current_count
    if matching_unresolved and go_live_status != "ambiguous":
        recon_status = "requires_validation"
        warning = _AMBIGUOUS_WARNING if not recon_ok else None
        report_status = "requires_review"
    elif not recon_ok:
        recon_status = "requires_validation"
        warning = _VALIDATION_MESSAGE
        report_status = "validation_failed"
    else:
        recon_status = "reconciled"
        warning = None
        report_status = "verified"
    if go_live_status == "ambiguous":
        report_status = "requires_review"
        recon_status = "requires_validation"
        warning = warning or "Go-Live is ambiguous. Configure the official Go-Live task."

    return DelayMappingSheet(
        report_status=report_status,
        go_live_status=go_live_status if go_live_status in {"calculated", "unavailable", "ambiguous"} else None,
        baseline_go_live=None if baseline_go_live is None else baseline_go_live.isoformat(),
        current_go_live=None if current_go_live is None else current_go_live.isoformat(),
        gross_working_day_shift=gross,
        shift_working_days=gross,
        holidays=holiday_count,
        net_working_day_shift=net,
        actual_shift_working_days=net,
        attributed_shift_days=attributed,
        unattributed_shift_days=0,
        unattributed_status=None,
        delay_shift_days=delay_shift,
        additional_shift_days=0,
        total_delayed_days=attributed,
        delayed_task_count=delay_count,
        additional_task_count=additional_count,
        matched_task_count=len(matched_baseline_ids),
        removed_task_count=removed_count,
        unchanged_task_count=unchanged_count,
        ahead_task_count=ahead_count,
        ambiguous_task_count=ambiguous_count,
        baseline_task_count=baseline_count,
        current_task_count=current_count,
        reconciliation_status=recon_status,
        reconciliation_warning=warning,
        calendar_source=calendar_source,
        matching_requires_validation=matching_unresolved,
        phase_attribution=[],
        owner_attribution=[],
        type_attribution=[],
        rows=rows,
        review_rows=review_rows,
        removed_rows=removed_rows,
    )


def match_task(
    current: PlanTaskData,
    baseline_index: dict[str, object],
) -> tuple[PlanTaskData | None, str]:
    """Match a current task to a baseline task. Never guess when the match is ambiguous."""

    by_id: dict[int, PlanTaskData] = baseline_index["by_id"]  # type: ignore[assignment]
    by_wbs: dict[str, list[PlanTaskData]] = baseline_index["by_wbs"]  # type: ignore[assignment]
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_hierarchy"]  # type: ignore[assignment]
    by_canonical: dict[str, list[PlanTaskData]] = baseline_index["by_canonical"]  # type: ignore[assignment]
    by_name_phase: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_name_phase"]  # type: ignore[assignment]
    current_tasks: list[PlanTaskData] = baseline_index["current_tasks"]  # type: ignore[assignment]

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
    parent = _parent_wbs(current.wbs)
    hierarchy_key = (_norm(current.name), _norm(parent))
    hier_hits = by_hierarchy.get(hierarchy_key, [])
    if len(hier_hits) == 1:
        return hier_hits[0], "hierarchy"
    if len(hier_hits) > 1:
        return None, "ambiguous"
    canon = _canonical_key(current, current_tasks)
    canon_hits = by_canonical.get(canon, [])
    if len(canon_hits) == 1:
        return canon_hits[0], "canonical"
    if len(canon_hits) > 1:
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
    current_tasks: list[PlanTaskData],
    parse_date,
) -> dict[str, object]:
    _ = parse_date
    scoped = _relevant_leaves(tasks)
    by_id = {task.id: task for task in scoped}
    by_wbs: dict[str, list[PlanTaskData]] = {}
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = {}
    by_canonical: dict[str, list[PlanTaskData]] = {}
    by_name_phase: dict[tuple[str, str], list[PlanTaskData]] = {}
    for task in scoped:
        wbs = (task.wbs or "").strip()
        if wbs:
            by_wbs.setdefault(wbs, []).append(task)
        parent = _parent_wbs(task.wbs)
        by_hierarchy.setdefault((_norm(task.name), _norm(parent)), []).append(task)
        by_canonical.setdefault(_canonical_key(task, tasks), []).append(task)
        by_name_phase.setdefault((_norm(task.name), str(task.outline_level)), []).append(task)
    return {
        "by_id": by_id,
        "by_wbs": by_wbs,
        "by_hierarchy": by_hierarchy,
        "by_canonical": by_canonical,
        "by_name_phase": by_name_phase,
        "current_tasks": current_tasks,
    }


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


def _potential_go_live_impact(
    item: dict,
    *,
    successors: dict[int, list[int]],
    go_live_task: PlanTaskData | None,
    net: int | None,
    holidays: set[date],
    parse_date,
) -> int:
    if net is None or net <= 0 or go_live_task is None:
        return 0
    task: PlanTaskData = item["task"]
    on_path = _reaches_task(successors, task.id, go_live_task.id)
    slack = task.total_slack_days
    has_float = slack is not None and slack > 0 and task.critical is False
    if item["task_type"] == "delay":
        shift = item["shift_days"] or 0
        if not on_path:
            return 0
        if slack is not None and shift and slack >= shift:
            return 0
        if has_float:
            return 0
        return shift
    if not on_path:
        return 0
    if has_float:
        return 0
    start = item.get("current_start")
    finish = item.get("current_finish")
    if start and finish and finish >= start:
        return len(_working_day_set(start, finish, holidays, inclusive_start=True))
    return 0


def _attribute_go_live_impact(items: list[dict], *, net: int) -> None:
    remaining = max(0, net)
    claimed: set[date] = set()
    ordered = sorted(
        items,
        key=lambda item: (
            0 if item["task_type"] == "delay" else 1,
            item.get("current_finish") or date.max,
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
                for day in _working_day_set(start, finish, set(), inclusive_start=item["task_type"] == "additional")
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
    baseline: PlanTaskData | None,
    task_type: str,
    *,
    shift_days: int | None,
    go_live_impact_days: int | None,
    successors: dict[int, list[int]],
    by_id: dict[int, PlanTaskData],
    go_live_task: PlanTaskData | None,
    parse_date,
    match_status: str,
    calculation_status: str,
    evidence_reason: str,
    calculation_source: str,
) -> DelayMappingRow:
    planned_start = parse_date(None if baseline is None else baseline.baseline_start)
    planned_finish = parse_date(None if baseline is None else baseline.baseline_finish)
    current_start = parse_date(task.actual_start) or parse_date(task.scheduled_start)
    current_finish = parse_date(task.actual_finish) or parse_date(task.scheduled_finish)
    names = _resolved_owner_names(task, tasks)
    successor_ids = list(successors.get(task.id, [])) or list(task.successor_ids)
    successor_names = list(task.successor_names) or _impacted_names(task.id, successors, by_id, go_live_task)[0]
    milestone_names = _impacted_names(task.id, successors, by_id, go_live_task)[1]
    parent = _containing_phase(tasks, phases, task)
    on_path = go_live_task is not None and _reaches_task(successors, task.id, go_live_task.id)
    impact_days = go_live_impact_days
    return DelayMappingRow(
        name=task.name,
        parent_name=None if parent is None else parent.name,
        wbs=(task.wbs or "").strip() or None,
        hierarchy_path=_canonical_key(task, tasks),
        task_type=task_type,  # type: ignore[arg-type]
        shift_days=None if task_type == "additional" else shift_days,
        delay_days=None if task_type == "additional" else shift_days,
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
        predecessor_names=list(task.predecessor_names),
        successor_names=successor_names,
        baseline_task_id=None if baseline is None else baseline.id,
        current_task_id=task.id,
        outline_number=(task.wbs or "").strip() or None,
        predecessor_ids=list(task.predecessor_ids),
        successor_ids=successor_ids,
        go_live_path_impact=on_path and (impact_days or 0) > 0,
        match_status=match_status,  # type: ignore[arg-type]
        calculation_status=calculation_status,  # type: ignore[arg-type]
        evidence_reason=evidence_reason,
        calculation_source=calculation_source,
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


def _select_go_live(
    tasks: list[PlanTaskData],
    as_of: date,
    contains,
    candidate_date,
) -> tuple[PlanTaskData | None, str]:
    explicit = [task for task in tasks if (task.gate or "").strip().casefold() in _EXPLICIT_GO_LIVE]
    named = explicit or [task for task in tasks if _is_go_live_task(task, contains)]
    if not named:
        return None, "unavailable"
    dated = [(task, when) for task in named if (when := candidate_date(task)) is not None]
    finishes = {when for _, when in dated}
    if len(named) > 1 and len(finishes) > 1:
        return None, "ambiguous"
    if not dated:
        return named[0], "calculated"
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

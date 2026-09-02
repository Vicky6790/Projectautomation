"""Delay Mapping sheet from one MPP.

Lists only tasks that:
- are marked Delay or Additional in the MPP column "Delay And Or Additional"
- sit on the predecessor path to Go-Live, or extend a critical predecessor summary
- shift Go-Live because Finish is later than Baseline Finish, Duration grew, or
  an inserted Delay/Additional task has no Baseline Finish
"""

from __future__ import annotations

from datetime import date

from app.models import DelayMappingRow, DelayMappingSheet, PlanTaskData, ProjectPlanData
from app.wsr.delay_engine import (
    _holiday_set,
    _holiday_weekdays_after,
    _owner_class,
    _owner_names,
    _select_go_live,
    _weekdays_after,
)
from app.wsr.facts import _candidate_date, _contains, parse_date, wsr_publish_date


def build_delay_sheet(plan: ProjectPlanData) -> DelayMappingSheet:
    as_of = parse_date(plan.status_date) or date.fromisoformat(wsr_publish_date())
    holidays = _holiday_set(plan, parse_date)
    calendar_source = (
        "project" if (plan.calendar_available or plan.holiday_dates) else "weekdays_fallback"
    )
    go_live_task, go_live_status = _select_go_live(plan.tasks, as_of, _contains, _candidate_date)
    pred_path_ids = _predecessor_path_ids(go_live_task, plan.tasks)
    go_live_id = None if go_live_task is None else go_live_task.id
    baseline_go_live = None
    current_go_live = None
    if go_live_task is not None and go_live_status != "ambiguous":
        baseline_go_live = parse_date(go_live_task.baseline0_finish or go_live_task.baseline_finish)
        current_go_live = parse_date(go_live_task.scheduled_finish or go_live_task.actual_finish)
        go_live_status = (
            "calculated"
            if baseline_go_live is not None and current_go_live is not None
            else "unavailable"
        )
    elif go_live_status != "ambiguous":
        go_live_status = "unavailable"

    gross = None
    holiday_count = None
    net = None
    if go_live_status == "calculated" and baseline_go_live is not None and current_go_live is not None:
        if current_go_live > baseline_go_live:
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

    rows: list[DelayMappingRow] = []
    for task in plan.tasks:
        row = _shifting_row(
            task,
            plan.tasks,
            pred_path_ids=pred_path_ids,
            go_live_id=go_live_id,
            holidays=holidays,
            calendar_source=calendar_source,
        )
        if row is not None:
            rows.append(row)
    rows = _fit_to_go_live_shift(rows, net)
    rows.sort(key=lambda item: ((item.wbs or ""), item.current_task_id or 0, item.name))
    delay_rows = [row for row in rows if row.task_type == "delay"]
    additional_rows = [row for row in rows if row.task_type == "additional"]
    total = sum(row.shift_days or 0 for row in rows)
    return DelayMappingSheet(
        report_status="verified",
        go_live_status=go_live_status,
        baseline_go_live=None if baseline_go_live is None else baseline_go_live.isoformat(),
        current_go_live=None if current_go_live is None else current_go_live.isoformat(),
        shift_working_days=gross,
        gross_working_day_shift=gross,
        holidays=holiday_count,
        net_working_day_shift=net,
        actual_shift_working_days=net,
        attributed_shift_days=total,
        delay_shift_days=sum(row.shift_days or 0 for row in delay_rows),
        additional_shift_days=sum(row.shift_days or 0 for row in additional_rows),
        total_delayed_days=total,
        delayed_task_count=len(delay_rows),
        additional_task_count=len(additional_rows),
        current_task_count=len(rows),
        calendar_source=calendar_source,
        as_of_date=as_of.isoformat(),
        rows=rows,
    )


def delay_days(planned_finish: str | None, actual_finish: str | None) -> int | None:
    planned = parse_date(planned_finish)
    actual = parse_date(actual_finish)
    if planned is None or actual is None:
        return None
    return (actual - planned).days


def classify_marked_type(value: str | None) -> str | None:
    text = " ".join((value or "").casefold().split())
    if not text:
        return None
    words = set(text.replace("/", " ").split())
    has_delay = bool(words & {"delay", "delayed"})
    has_additional = bool(words & {"additional", "addnl", "add"})
    if has_delay and has_additional:
        return None
    if has_additional:
        return "additional"
    if has_delay:
        return "delay"
    return None


def _shifting_row(
    task: PlanTaskData,
    tasks: list[PlanTaskData],
    *,
    pred_path_ids: set[int],
    go_live_id: int | None,
    holidays: set[date],
    calendar_source: str,
) -> DelayMappingRow | None:
    if task.is_summary or not (task.name or "").strip():
        return None
    if go_live_id is not None and task.id == go_live_id:
        return None
    marked = classify_marked_type(task.delay_or_additional)
    if marked is None:
        return None
    if not _shifts_go_live(task, tasks, pred_path_ids=pred_path_ids, go_live_id=go_live_id):
        return None
    planned = parse_date(task.baseline0_finish) or parse_date(task.baseline_finish)
    finish = parse_date(task.scheduled_finish) or parse_date(task.actual_finish)
    shift, source = _task_shift(
        task,
        planned=planned,
        finish=finish,
        holidays=holidays,
        calendar_source=calendar_source,
    )
    if not shift or shift <= 0:
        return None
    names = _owner_names(task)
    parent_name = _phase_name(task, tasks)
    return DelayMappingRow(
        name=task.name,
        parent_name=parent_name,
        wbs=task.wbs,
        outline_number=task.wbs,
        task_type=marked,  # type: ignore[arg-type]
        delay_days=shift,
        shift_days=shift,
        owner=" & ".join(names) if names else None,
        owner_class=_owner_class(names),  # type: ignore[arg-type]
        planned_start=task.baseline_start,
        planned_finish=None if planned is None else planned.isoformat(),
        revised_start=task.scheduled_start or task.actual_start,
        revised_finish=None if finish is None else finish.isoformat(),
        predecessor_names=list(task.predecessor_names),
        predecessor_ids=list(task.predecessor_ids),
        successor_names=list(task.successor_names),
        successor_ids=list(task.successor_ids),
        current_task_id=task.id,
        go_live_path_impact=True,
        match_status="matched",
        calculation_status="calculated",
        evidence_reason=_evidence(marked, shift, source),
        calculation_source=source,
        source="MPP",
        critical=task.critical,
    )


def _predecessor_path_ids(go_live: PlanTaskData | None, tasks: list[PlanTaskData]) -> set[int]:
    if go_live is None:
        return set()
    preds = {task.id: list(task.predecessor_ids) for task in tasks}
    on: set[int] = set()
    queue = [go_live.id]
    while queue:
        nid = queue.pop()
        if nid in on:
            continue
        on.add(nid)
        queue.extend(preds.get(nid, []))
    return on


def _shifts_go_live(
    task: PlanTaskData,
    tasks: list[PlanTaskData],
    *,
    pred_path_ids: set[int],
    go_live_id: int | None,
) -> bool:
    if go_live_id is None:
        if task.critical is True:
            return True
        return task.total_slack_days is not None and task.total_slack_days <= 0
    if task.id in pred_path_ids:
        return True
    parent = _parent_summary(task, tasks)
    finish = parse_date(task.scheduled_finish) or parse_date(task.actual_finish)
    parent_finish = None
    if parent is not None:
        parent_finish = parse_date(parent.scheduled_finish) or parse_date(parent.actual_finish)
    drives_parent = (
        parent is not None
        and finish is not None
        and parent_finish is not None
        and finish == parent_finish
    )
    if not drives_parent:
        return False
    if task.critical is True:
        return True
    return parent is not None and parent.critical is True


def _fit_to_go_live_shift(rows: list[DelayMappingRow], net: int | None) -> list[DelayMappingRow]:
    if net is None or net < 0:
        return rows
    total = sum(row.shift_days or 0 for row in rows)
    if total <= net:
        return rows
    ordered = sorted(
        rows,
        key=lambda row: (
            0 if row.critical is True else 1,
            -(row.shift_days or 0),
            row.revised_finish or "",
            row.current_task_id or 0,
        ),
    )
    kept: list[DelayMappingRow] = []
    used = 0
    for row in ordered:
        days = row.shift_days or 0
        if days <= 0 or used >= net:
            continue
        if used > 0 and used + days > net:
            continue
        if used == 0 and days > net:
            row.shift_days = net
            row.delay_days = net
            days = net
        kept.append(row)
        used += days
        if used >= net:
            break
    return kept


def _parent_summary(task: PlanTaskData, tasks: list[PlanTaskData]) -> PlanTaskData | None:
    wbs_map = {(item.wbs or "").strip(): item for item in tasks if (item.wbs or "").strip()}
    code = (task.wbs or "").strip()
    while "." in code:
        code = code.rsplit(".", 1)[0]
        parent = wbs_map.get(code)
        if parent is not None and parent.is_summary:
            return parent
    return None


def _task_shift(
    task: PlanTaskData,
    *,
    planned: date | None,
    finish: date | None,
    holidays: set[date],
    calendar_source: str,
) -> tuple[int, str] | tuple[None, None]:
    if planned is not None and finish is not None and finish > planned:
        finish_shift = _weekdays_after(planned, finish)
        if calendar_source == "project":
            finish_shift = max(0, finish_shift - _holiday_weekdays_after(planned, finish, holidays))
        if finish_shift > 0:
            return finish_shift, "finish_vs_baseline"
    growth = _duration_growth(task)
    if growth:
        return growth, "duration_vs_baseline"
    if planned is None:
        inserted = _positive_duration(task)
        if inserted:
            return inserted, "inserted_duration"
    return None, None


def _duration_growth(task: PlanTaskData) -> int | None:
    current = task.duration_days
    planned = task.baseline0_duration_days
    if current is None or planned is None:
        return None
    extra = int(round(current - planned))
    return extra if extra > 0 else None


def _positive_duration(task: PlanTaskData) -> int | None:
    if task.duration_days is None:
        return None
    days = int(round(task.duration_days))
    return days if days > 0 else None


def _phase_name(task: PlanTaskData, tasks: list[PlanTaskData]) -> str | None:
    parent = _parent_summary(task, tasks)
    if parent is None:
        return None
    name = (parent.name or "").strip()
    return name or None


def _evidence(marked: str, shift: int, source: str) -> str:
    kind = "Additional" if marked == "additional" else "Delay"
    if source == "duration_vs_baseline":
        return (
            f"{kind} task on the Go-Live predecessor path. "
            f"Duration is longer than Baseline Duration by {shift} day(s)."
        )
    if source == "inserted_duration":
        return (
            f"{kind} task on the Go-Live predecessor path. "
            f"No Baseline Finish; Duration is {shift} day(s)."
        )
    return (
        f"{kind} task on the Go-Live predecessor path. "
        f"Finish is later than Baseline Finish by {shift} working day(s)."
    )

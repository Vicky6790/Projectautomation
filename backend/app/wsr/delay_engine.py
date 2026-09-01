"""Delay Sheet: copy every MPP task whose Baseline Finish is the text NA."""

from __future__ import annotations

import logging
from datetime import date

from app.models import (
    DelayMappingRow,
    DelayMappingSheet,
    PhaseStatus,
    PlanTaskData,
    ProjectPlanData,
)

logger = logging.getLogger(__name__)

_NA_TOKENS = frozenset({"NA", "N/A", "N.A."})


def baseline_finish_is_na(value: str | None) -> bool:
    """True only for explicit NA tokens. Blank, null, and dates are not NA."""
    if value is None:
        return False
    text = value.strip()
    if not text:
        return False
    return text.upper() in _NA_TOKENS


def build_delay_mapping(
    plan: ProjectPlanData,
    as_of: date,
    phases: list[PhaseStatus],
    go_live_date: date | None,
    baseline_plan: ProjectPlanData | None = None,
) -> DelayMappingSheet:
    _ = as_of, phases, go_live_date, baseline_plan
    tasks = list(plan.tasks)
    na_tasks = [task for task in tasks if baseline_finish_is_na(task.baseline_finish)]
    rows = [_na_row(task) for task in na_tasks]
    invalid = [row for row in rows if not baseline_finish_is_na(row.planned_finish)]
    total = len(tasks)
    na_count = len(na_tasks)
    row_count = len(rows)
    debug = (
        f"Total tasks read: {total}\n"
        f"Tasks with Baseline Finish = NA: {na_count}\n"
        f"Delay Sheet rows generated: {row_count}"
    )
    logger.info(debug)
    mismatch = bool(invalid) or row_count != na_count
    return DelayMappingSheet(
        report_status="verified" if not mismatch else "validation_failed",
        go_live_status=None,
        delayed_task_count=0,
        additional_task_count=na_count,
        current_task_count=total,
        baseline_task_count=total,
        reconciliation_status="reconciled" if not mismatch else "requires_validation",
        reconciliation_warning=debug if mismatch else None,
        calendar_source=None,
        rows=rows,
        review_rows=[],
        removed_rows=[],
    )


def _na_row(task: PlanTaskData) -> DelayMappingRow:
    token = (task.baseline_finish or "").strip()
    return DelayMappingRow(
        name=task.name,
        wbs=(task.wbs or "").strip() or None,
        task_type="additional",
        planned_finish=token or None,
        revised_start=task.scheduled_start,
        revised_finish=task.scheduled_finish,
        predecessor_names=list(task.predecessor_names),
        predecessor_ids=list(task.predecessor_ids),
        current_task_id=task.id,
        baseline_task_id=task.id,
        outline_number=(task.wbs or "").strip() or None,
        match_status="additional",
        calculation_status="calculated",
        calculation_source="baseline_finish_na",
        evidence_reason="Baseline Finish is NA.",
    )

"""Read-only Baseline vs Current match dump. Does not compute Go-Live impact."""

from __future__ import annotations

import csv
import io
from datetime import date

from app.models import (
    DelayMappingDiagnostic,
    DelayMappingDiagnosticReconcile,
    DelayMappingDiagnosticRemoved,
    DelayMappingDiagnosticRow,
    PlanTaskData,
    ProjectPlanData,
)
from app.wsr.delay_engine import (
    _baseline_index,
    _compare_finish,
    _parent_wbs,
    _relevant_leaves,
    match_task,
)
from app.wsr.facts import parse_date

_MATCHED_CLASSES = frozenset(
    {"MATCHED", "DELAYED", "AHEAD", "UNCHANGED", "BASELINE_DATA_MISSING"}
)
_CONFIDENCE = {
    "id": "high",
    "canonical": "high",
    "hierarchy": "medium",
    "ambiguous": "low",
    "unmatched": "none",
}
CSV_COLUMNS = (
    "Current Task ID",
    "Current Task Name",
    "Current Outline Number",
    "Current Outline Level",
    "Current Parent",
    "Current Phase",
    "Current Start",
    "Current Finish",
    "Current Predecessors",
    "Baseline Matching Task ID",
    "Baseline Task Name",
    "Baseline Outline Number",
    "Baseline Finish",
    "Baseline Predecessors",
    "Match Method",
    "Match Confidence",
    "Classification",
)


def build_delay_mapping_diagnostic(
    current: ProjectPlanData,
    baseline: ProjectPlanData,
) -> DelayMappingDiagnostic:
    current_leaves = _relevant_leaves(current.tasks)
    baseline_leaves = _relevant_leaves(baseline.tasks)
    index = _baseline_index(baseline.tasks, current.tasks, parse_date=parse_date)
    by_current_id = {task.id: task for task in current.tasks}
    by_baseline_id = {task.id: task for task in baseline.tasks}

    rows: list[DelayMappingDiagnosticRow] = []
    matched_baseline_ids: set[int] = set()
    duplicate_baseline_ids: set[int] = set()
    for task in current_leaves:
        matched, source = match_task(task, index)
        row = _current_row(task, matched, source, current.tasks, baseline.tasks, by_current_id, by_baseline_id)
        if matched is not None:
            if matched.id in matched_baseline_ids:
                duplicate_baseline_ids.add(matched.id)
            matched_baseline_ids.add(matched.id)
        rows.append(row)

    removed: list[DelayMappingDiagnosticRemoved] = []
    for task in baseline_leaves:
        if task.id in matched_baseline_ids:
            continue
        removed.append(
            DelayMappingDiagnosticRemoved(
                baseline_task_id=task.id,
                baseline_task_name=task.name,
                baseline_outline_number=(task.wbs or "").strip() or None,
                baseline_finish=_iso(_compare_finish(task, two_file=True, parse_date=parse_date)),
                baseline_predecessors=_pred_label(task, by_baseline_id),
            )
        )

    matched_count = sum(1 for row in rows if row.classification in _MATCHED_CLASSES)
    additional_count = sum(1 for row in rows if row.classification == "ADDITIONAL")
    ambiguous_count = sum(1 for row in rows if row.classification == "AMBIGUOUS")
    current_count = len(current_leaves)
    baseline_count = len(baseline_leaves)
    removed_count = len(removed)
    current_ok = matched_count + additional_count == current_count
    baseline_ok = matched_count + removed_count == baseline_count and not duplicate_baseline_ids

    unmatched_current = [
        f"{row.current_task_id}: {row.current_task_name} [{row.classification}]"
        for row in rows
        if row.classification not in _MATCHED_CLASSES and row.classification != "ADDITIONAL"
    ]
    unmatched_baseline = [
        f"{item.baseline_task_id}: {item.baseline_task_name}" for item in removed
    ]
    if duplicate_baseline_ids:
        unmatched_current.append(
            "Duplicate baseline matches: " + ", ".join(str(item) for item in sorted(duplicate_baseline_ids))
        )
    if not current_ok and not unmatched_current:
        unmatched_current = [
            f"{row.current_task_id}: {row.current_task_name} [{row.classification}]"
            for row in rows
            if row.classification == "AMBIGUOUS"
        ]

    return DelayMappingDiagnostic(
        rows=rows,
        removed_tasks=removed,
        reconciliation=DelayMappingDiagnosticReconcile(
            baseline_executable_task_count=baseline_count,
            current_executable_task_count=current_count,
            matched_count=matched_count,
            additional_count=additional_count,
            removed_count=removed_count,
            ambiguous_count=ambiguous_count,
            matched_plus_additional=matched_count + additional_count,
            matched_plus_removed=matched_count + removed_count,
            current_reconciles=current_ok,
            baseline_reconciles=baseline_ok,
            unmatched_current_tasks=unmatched_current,
            unmatched_baseline_tasks=[] if baseline_ok else unmatched_baseline,
        ),
    )


def diagnostic_csv(payload: DelayMappingDiagnostic) -> str:
    buffer = io.StringIO()
    recon = payload.reconciliation
    buffer.write("RECONCILIATION\n")
    writer = csv.writer(buffer)
    writer.writerow(["Baseline executable task count", recon.baseline_executable_task_count])
    writer.writerow(["Current executable task count", recon.current_executable_task_count])
    writer.writerow(["Matched count", recon.matched_count])
    writer.writerow(["Additional count", recon.additional_count])
    writer.writerow(["Removed count", recon.removed_count])
    writer.writerow(["Ambiguous count", recon.ambiguous_count])
    writer.writerow(["Matched + Additional", recon.matched_plus_additional])
    writer.writerow(["Matched + Removed", recon.matched_plus_removed])
    writer.writerow(["Current reconciles", recon.current_reconciles])
    writer.writerow(["Baseline reconciles", recon.baseline_reconciles])
    for item in recon.unmatched_current_tasks:
        writer.writerow(["Unmatched current task", item])
    for item in recon.unmatched_baseline_tasks:
        writer.writerow(["Unmatched baseline task", item])
    buffer.write("\nCURRENT TASKS\n")
    writer.writerow(CSV_COLUMNS)
    for row in payload.rows:
        writer.writerow(
            [
                row.current_task_id,
                row.current_task_name,
                row.current_outline_number or "",
                row.current_outline_level,
                row.current_parent or "",
                row.current_phase or "",
                row.current_start or "",
                row.current_finish or "",
                row.current_predecessors or "",
                row.baseline_matching_task_id or "",
                row.baseline_task_name or "",
                row.baseline_outline_number or "",
                row.baseline_finish or "",
                row.baseline_predecessors or "",
                row.match_method,
                row.match_confidence,
                row.classification,
            ]
        )
    if payload.removed_tasks:
        buffer.write("\nREMOVED BASELINE TASKS\n")
        writer.writerow(
            [
                "Baseline Task ID",
                "Baseline Task Name",
                "Baseline Outline Number",
                "Baseline Finish",
                "Baseline Predecessors",
            ]
        )
        for item in payload.removed_tasks:
            writer.writerow(
                [
                    item.baseline_task_id,
                    item.baseline_task_name,
                    item.baseline_outline_number or "",
                    item.baseline_finish or "",
                    item.baseline_predecessors or "",
                ]
            )
    return buffer.getvalue()


def _current_row(
    task: PlanTaskData,
    matched: PlanTaskData | None,
    source: str,
    current_tasks: list[PlanTaskData],
    baseline_tasks: list[PlanTaskData],
    by_current_id: dict[int, PlanTaskData],
    by_baseline_id: dict[int, PlanTaskData],
) -> DelayMappingDiagnosticRow:
    current_start = parse_date(task.actual_start) or parse_date(task.scheduled_start)
    current_finish = parse_date(task.actual_finish) or parse_date(task.scheduled_finish)
    baseline_finish = _compare_finish(matched, two_file=True, parse_date=parse_date)
    classification = _classification(source, matched, current_finish, baseline_finish)
    method = source if source != "unmatched" else "none"
    return DelayMappingDiagnosticRow(
        current_task_id=task.id,
        current_task_name=task.name,
        current_outline_number=(task.wbs or "").strip() or None,
        current_outline_level=task.outline_level,
        current_parent=_display_parent(task, current_tasks),
        current_phase=_display_phase(task, current_tasks),
        current_start=_iso(current_start),
        current_finish=_iso(current_finish),
        current_predecessors=_pred_label(task, by_current_id),
        baseline_matching_task_id=None if matched is None else matched.id,
        baseline_task_name=None if matched is None else matched.name,
        baseline_outline_number=None if matched is None else ((matched.wbs or "").strip() or None),
        baseline_finish=_iso(baseline_finish),
        baseline_predecessors=None if matched is None else _pred_label(matched, by_baseline_id),
        match_method=method,
        match_confidence=_CONFIDENCE.get(source, "none"),
        classification=classification,
        baseline_finish_source=_finish_source(matched, baseline_finish),
    )


def _classification(
    source: str,
    matched: PlanTaskData | None,
    current_finish: date | None,
    baseline_finish: date | None,
) -> str:
    if source == "ambiguous":
        return "AMBIGUOUS"
    if matched is None:
        return "ADDITIONAL"
    if baseline_finish is None:
        return "BASELINE_DATA_MISSING"
    if current_finish is None:
        return "MATCHED"
    if current_finish > baseline_finish:
        return "DELAYED"
    if current_finish < baseline_finish:
        return "AHEAD"
    return "UNCHANGED"


def _finish_source(matched: PlanTaskData | None, used: date | None) -> str | None:
    if matched is None or used is None:
        return None
    field = parse_date(matched.baseline_finish)
    if field == used:
        return "baseline_finish"
    scheduled = parse_date(matched.scheduled_finish)
    if scheduled == used:
        return "scheduled_finish"
    return None


def _display_parent(task: PlanTaskData, tasks: list[PlanTaskData]) -> str | None:
    parent = _wbs_map(tasks).get(_parent_wbs(task.wbs))
    name = None if parent is None else (parent.name or "").strip()
    return name or None


def _display_phase(task: PlanTaskData, tasks: list[PlanTaskData]) -> str | None:
    wbs_map = _wbs_map(tasks)
    parent = wbs_map.get(_parent_wbs(task.wbs))
    phase = parent
    while phase is not None and phase.outline_level > 1:
        phase = wbs_map.get(_parent_wbs(phase.wbs))
    name = None if phase is None else (phase.name or "").strip()
    return name or None


def _wbs_map(tasks: list[PlanTaskData]) -> dict[str, PlanTaskData]:
    return {(item.wbs or "").strip(): item for item in tasks if (item.wbs or "").strip()}


def _pred_label(task: PlanTaskData, by_id: dict[int, PlanTaskData]) -> str | None:
    names = [name.strip() for name in task.predecessor_names if name and name.strip()]
    if names:
        return ", ".join(names)
    resolved: list[str] = []
    for pred_id in task.predecessor_ids:
        pred = by_id.get(pred_id)
        resolved.append(pred.name if pred is not None else str(pred_id))
    return ", ".join(resolved) or None


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()

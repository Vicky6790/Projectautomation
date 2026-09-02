"""Detect tasks present in Current MPP and absent from Baseline MPP.

Matching never uses Microsoft Project row IDs (those shift when tasks are inserted).
Identity is Unique ID / GUID when those keys are reliable across both files, otherwise
WBS + Task Name, otherwise Task Name + parent. Ambiguous keys are not guessed.
"""

from __future__ import annotations

import logging

from app.models import DelayMappingRow, DelayMappingSheet, PlanTaskData, ProjectPlanData

logger = logging.getLogger(__name__)

_UNMATCHED_REASON = "Not found in Baseline MPP"
_SOURCE = "Current MPP"
_UNIQUE_ID_UNRELIABLE = (
    "Unique ID matching skipped: Unique IDs are not reliable across these MPP files "
    "(no consistent Unique ID and name overlap, or Unique ID collisions with different names). "
    "Matching uses WBS + Task Name, then Task Name + Parent."
)
_GUID_UNRELIABLE = (
    "GUID matching skipped: GUIDs are not reliable across these MPP files "
    "(no consistent GUID and name overlap, or GUID collisions with different names)."
)
_AMBIGUOUS_WARNING = (
    "Some Current MPP tasks could not be matched safely because more than one Baseline task "
    "shares the same key. Those tasks were not classified as New Task."
)


def build_new_task_mapping(
    current_plan: ProjectPlanData,
    baseline_plan: ProjectPlanData,
) -> DelayMappingSheet:
    current_tasks = list(current_plan.tasks)
    baseline_tasks = list(baseline_plan.tasks)
    guid_ok = _identifier_reliable(current_tasks, baseline_tasks, _guid_key)
    unique_ok = _identifier_reliable(current_tasks, baseline_tasks, lambda task: task.id)
    baseline_index = _index(baseline_tasks)
    used: set[int] = set()
    matched = 0
    rows: list[DelayMappingRow] = []
    review_rows: list[DelayMappingRow] = []
    limitations: list[str] = []

    if any(_guid_key(task) for task in current_tasks + baseline_tasks) and not guid_ok:
        limitations.append(_GUID_UNRELIABLE)
    if not unique_ok:
        limitations.append(_UNIQUE_ID_UNRELIABLE)

    for task in current_tasks:
        hit, method, status = _match_task(
            task,
            current_tasks,
            baseline_index,
            used,
            guid_ok=guid_ok,
            unique_ok=unique_ok,
        )
        if status == "matched" and hit is not None:
            used.add(hit.id)
            matched += 1
            continue
        if status == "ambiguous":
            review_rows.append(
                _row(
                    task,
                    current_tasks,
                    method=method,
                    reason=(
                        "Multiple Baseline tasks share the same key. "
                        "Skipped unsafe match."
                    ),
                    match_status="ambiguous",
                    calculation_status="ambiguous_match",
                )
            )
            continue
        rows.append(
            _row(
                task,
                current_tasks,
                method=method,
                reason=_UNMATCHED_REASON,
                match_status="new_task",
                calculation_status=None,
            )
        )
        _log_new_task(task, current_tasks, method)

    new_count = len(rows)
    logger.info("Baseline MPP total tasks: %s", len(baseline_tasks))
    logger.info("Current MPP total tasks: %s", len(current_tasks))
    logger.info("Matched existing tasks: %s", matched)
    logger.info("New tasks detected: %s", new_count)
    logger.info("Delay Mapping new-task rows: %s", new_count)

    if review_rows:
        limitations.append(_AMBIGUOUS_WARNING)

    warning = " ".join(limitations) if limitations else None
    return DelayMappingSheet(
        report_status="requires_review" if warning else "verified",
        matching_requires_validation=bool(warning),
        reconciliation_status="requires_validation" if warning else "reconciled",
        reconciliation_warning=warning,
        baseline_task_count=len(baseline_tasks),
        current_task_count=len(current_tasks),
        matched_task_count=matched,
        new_task_count=new_count,
        additional_task_count=new_count,
        ambiguous_task_count=len(review_rows),
        rows=rows,
        review_rows=review_rows,
    )


def _match_task(
    current: PlanTaskData,
    current_tasks: list[PlanTaskData],
    baseline_index: dict[str, object],
    used: set[int],
    *,
    guid_ok: bool,
    unique_ok: bool,
) -> tuple[PlanTaskData | None, str, str]:
    by_guid: dict[str, list[PlanTaskData]] = baseline_index["by_guid"]  # type: ignore[assignment]
    by_id: dict[int, PlanTaskData] = baseline_index["by_id"]  # type: ignore[assignment]
    by_wbs_name: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_wbs_name"]  # type: ignore[assignment]
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = baseline_index["by_hierarchy"]  # type: ignore[assignment]

    if guid_ok:
        guid = _guid_key(current)
        if guid:
            status, hit = _unique_available(by_guid.get(guid, []), used)
            if status == "matched":
                return hit, "guid", "matched"
            if status == "ambiguous":
                return None, "guid", "ambiguous"

    if unique_ok:
        hit = by_id.get(current.id)
        if hit is not None and hit.id not in used:
            return hit, "unique_id", "matched"
        # Row IDs shift on insert; when Unique IDs are the identity, an unseen
        # Unique ID is a new task. Do not fall through to WBS numbers.
        return None, "unique_id", "unmatched"

    wbs = (current.wbs or "").strip()
    if wbs:
        key = (_norm(wbs), _norm(current.name))
        status, hit = _unique_available(by_wbs_name.get(key, []), used)
        if status == "matched":
            return hit, "wbs_name", "matched"
        if status == "ambiguous":
            return None, "wbs_name", "ambiguous"

    hierarchy_key = (_norm(current.name), _parent_name(current, current_tasks))
    status, hit = _unique_available(by_hierarchy.get(hierarchy_key, []), used)
    if status == "matched":
        return hit, "hierarchy", "matched"
    if status == "ambiguous":
        return None, "hierarchy", "ambiguous"

    method = "wbs_name" if wbs else "hierarchy"
    return None, method, "unmatched"


def _unique_available(
    hits: list[PlanTaskData],
    used: set[int],
) -> tuple[str, PlanTaskData | None]:
    available = [task for task in hits if task.id not in used]
    if len(available) == 1:
        return "matched", available[0]
    if len(available) > 1:
        return "ambiguous", None
    return "missing", None


def _identifier_reliable(
    current_tasks: list[PlanTaskData],
    baseline_tasks: list[PlanTaskData],
    key_fn,
) -> bool:
    baseline_by_key: dict[object, list[PlanTaskData]] = {}
    for task in baseline_tasks:
        key = key_fn(task)
        if key is None or key == "":
            continue
        baseline_by_key.setdefault(key, []).append(task)
    confirmed = 0
    for task in current_tasks:
        key = key_fn(task)
        if key is None or key == "":
            continue
        hits = baseline_by_key.get(key, [])
        if not hits:
            continue
        if len(hits) != 1:
            return False
        if _norm(task.name) != _norm(hits[0].name):
            return False
        confirmed += 1
    return confirmed > 0


def _index(tasks: list[PlanTaskData]) -> dict[str, object]:
    by_id = {task.id: task for task in tasks}
    by_guid: dict[str, list[PlanTaskData]] = {}
    by_wbs_name: dict[tuple[str, str], list[PlanTaskData]] = {}
    by_hierarchy: dict[tuple[str, str], list[PlanTaskData]] = {}
    for task in tasks:
        guid = _guid_key(task)
        if guid:
            by_guid.setdefault(guid, []).append(task)
        wbs = (task.wbs or "").strip()
        if wbs:
            by_wbs_name.setdefault((_norm(wbs), _norm(task.name)), []).append(task)
        by_hierarchy.setdefault((_norm(task.name), _parent_name(task, tasks)), []).append(task)
    return {
        "by_id": by_id,
        "by_guid": by_guid,
        "by_wbs_name": by_wbs_name,
        "by_hierarchy": by_hierarchy,
        "tasks": tasks,
    }


def _row(
    task: PlanTaskData,
    tasks: list[PlanTaskData],
    *,
    method: str,
    reason: str,
    match_status: str,
    calculation_status: str | None,
) -> DelayMappingRow:
    parent = _parent_task(task, tasks)
    task_type = "new_task" if match_status == "new_task" else "unavailable"
    return DelayMappingRow(
        name=task.name,
        parent_name=None if parent is None else parent.name,
        wbs=task.wbs,
        outline_number=task.wbs,
        hierarchy_path=_hierarchy_path(task, tasks),
        task_type=task_type,
        planned_finish=task.baseline_finish,
        revised_start=task.scheduled_start,
        revised_finish=task.scheduled_finish,
        predecessor_names=list(task.predecessor_names),
        predecessor_ids=list(task.predecessor_ids),
        current_task_id=task.id,
        match_status=match_status,  # type: ignore[arg-type]
        calculation_status=calculation_status,  # type: ignore[arg-type]
        evidence_reason=reason,
        calculation_source=method,
        source=_SOURCE if match_status == "new_task" else None,
    )


def _log_new_task(task: PlanTaskData, tasks: list[PlanTaskData], method: str) -> None:
    parent = _parent_task(task, tasks)
    logger.info("NEW TASK:")
    logger.info("Current Task ID: %s", task.id)
    logger.info("Task Name: %s", task.name)
    logger.info("WBS: %s", (task.wbs or "").strip() or "Unavailable")
    logger.info("Parent: %s", parent.name if parent is not None else "Unavailable")
    logger.info("Matching method: %s", method)
    logger.info("Reason: %s", _UNMATCHED_REASON)


def _guid_key(task: PlanTaskData) -> str:
    return (task.guid or "").strip().casefold()


def _parent_wbs(wbs: str | None) -> str:
    text = (wbs or "").strip()
    if "." not in text:
        return ""
    return text.rsplit(".", 1)[0]


def _parent_task(task: PlanTaskData, tasks: list[PlanTaskData]) -> PlanTaskData | None:
    wbs_map = {(item.wbs or "").strip(): item for item in tasks if (item.wbs or "").strip()}
    return wbs_map.get(_parent_wbs(task.wbs))


def _parent_name(task: PlanTaskData, tasks: list[PlanTaskData]) -> str:
    parent = _parent_task(task, tasks)
    return _norm(None if parent is None else parent.name)


def _hierarchy_path(task: PlanTaskData, tasks: list[PlanTaskData]) -> str:
    parts = [task.name]
    current = _parent_task(task, tasks)
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        parts.append(current.name)
        current = _parent_task(current, tasks)
    return " > ".join(reversed(parts))


def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().split())

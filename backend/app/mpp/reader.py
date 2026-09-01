from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from app.errors import AppError
from app.models import (
    PlanAssignmentData,
    PlanPhaseData,
    PlanRelationData,
    PlanResourceData,
    PlanTaskData,
    ProjectPlanData,
)
from app.mpp.bridge import ensure_jvm
from app.wsr.facts import select_phase_summaries


def read_mpp_bytes(content: bytes, filename: str = "plan.mpp") -> ProjectPlanData:
    if not content:
        raise AppError(400, "UNREADABLE_MPP", "The MPP file could not be read")
    suffix = Path(filename).suffix or ".mpp"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(content)
        tmp.close()
        return read_mpp_file(tmp.name)
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass


def read_mpp_file(path: str) -> ProjectPlanData:
    ensure_jvm()
    from org.mpxj.reader import UniversalProjectReader

    try:
        project = UniversalProjectReader().read(path)
    except Exception as exc:  # noqa: BLE001 - invalid MPP is a user error
        raise AppError(400, "UNREADABLE_MPP", "The MPP file could not be read") from exc
    if project is None:
        raise AppError(400, "UNREADABLE_MPP", "The MPP file could not be read")
    return project_from_mpxj(project)


def project_from_mpxj(project) -> ProjectPlanData:
    props = project.getProjectProperties()
    name = str(props.getProjectTitle() or "").strip() or "Untitled plan"
    owner = _first_text(props.getManager(), props.getAuthor())
    status_date = iso_date(props.getStatusDate())
    gate_field = _gate_field(project)
    calendar = project.getDefaultCalendar()

    resources: list[PlanResourceData] = []
    for resource in project.getResources():
        resource_name = resource.getName()
        if not resource_name:
            continue
        unique_id = resource.getUniqueID()
        if unique_id is None:
            continue
        resources.append(
            PlanResourceData(
                id=int(unique_id),
                name=str(resource_name),
                max_units=_number(resource.getMaxUnits()),
            )
        )

    tasks: list[PlanTaskData] = []
    has_actuals = False
    for task in project.getTasks():
        task_name = task.getName()
        if not task_name:
            continue
        unique_id = task.getUniqueID()
        if unique_id is None:
            continue
        baseline_start = iso_date(task.getBaselineStart())
        baseline_finish = iso_date(task.getBaselineFinish())
        scheduled_start = iso_date(task.getStart())
        scheduled_finish = iso_date(task.getFinish())
        actual_start = iso_date(task.getActualStart())
        actual_finish = iso_date(task.getActualFinish())
        percent = _percent(task.getPercentageComplete())
        planned_work = duration_hours(task.getWork(), calendar)
        actual_work = duration_hours(task.getActualWork(), calendar)
        if actual_start or actual_finish or percent > 0 or (actual_work or 0) > 0:
            has_actuals = True
        predecessor_ids: list[int] = []
        predecessor_names: list[str] = []
        predecessor_links: list[PlanRelationData] = []
        for relation in task.getPredecessors() or []:
            pred = relation.getPredecessorTask()
            if pred is None or pred.getUniqueID() is None:
                continue
            pred_id = int(pred.getUniqueID())
            predecessor_ids.append(pred_id)
            pred_name = pred.getName()
            if pred_name:
                predecessor_names.append(str(pred_name))
            predecessor_links.append(
                PlanRelationData(
                    predecessor_id=pred_id,
                    relation_type=_relation_type(relation),
                    lag_days=_lag_days(relation, calendar),
                )
            )
        successor_ids: list[int] = []
        successor_names: list[str] = []
        for relation in task.getSuccessors() or []:
            succ = _successor_task(relation)
            if succ is None or succ.getUniqueID() is None:
                continue
            successor_ids.append(int(succ.getUniqueID()))
            succ_name = succ.getName()
            if succ_name:
                successor_names.append(str(succ_name))
        assignments: list[PlanAssignmentData] = []
        for assignment in task.getResourceAssignments() or []:
            mapped = _assignment(assignment, calendar)
            if mapped is not None:
                assignments.append(mapped)
                if (mapped.actual_work_hours or 0) > 0:
                    has_actuals = True
        tasks.append(
            PlanTaskData(
                id=int(unique_id),
                name=str(task_name),
                wbs=_wbs_code(task),
                outline_level=int(task.getOutlineLevel()) if task.getOutlineLevel() is not None else 1,
                is_summary=bool(task.getSummary()),
                is_milestone=bool(task.getMilestone()),
                set_name=_text_field(task, 1),
                gate=_gate_value(task, gate_field),
                baseline_start=baseline_start,
                baseline_finish=baseline_finish,
                scheduled_start=scheduled_start,
                scheduled_finish=scheduled_finish,
                actual_start=actual_start,
                actual_finish=actual_finish,
                percent_complete=percent,
                predecessor_ids=predecessor_ids,
                predecessor_names=predecessor_names,
                predecessor_links=predecessor_links,
                successor_ids=successor_ids,
                successor_names=successor_names,
                comparison_available=bool(baseline_start or baseline_finish),
                planned_work_hours=planned_work,
                actual_work_hours=actual_work,
                assignments=assignments,
                total_slack_days=_slack_days(task, calendar),
                critical=_critical(task),
                calendar_name=_calendar_name(task, calendar),
            )
        )
    by_id = {task.id: task for task in tasks}
    for task in tasks:
        if task.successor_ids:
            continue
        for pred_id in task.predecessor_ids:
            pred = by_id.get(pred_id)
            if pred is None:
                continue
            if task.id not in pred.successor_ids:
                pred.successor_ids.append(task.id)
                pred.successor_names.append(task.name)
    holidays = _holiday_dates(calendar)
    return ProjectPlanData(
        name=name,
        owner=owner,
        status_date=status_date,
        has_actuals=has_actuals,
        planned_only=not has_actuals,
        tasks=tasks,
        resources=resources,
        phases=[_phase(task) for task in select_phase_summaries(tasks, project_name=name)],
        calendar_available=holidays is not None,
        holiday_dates=holidays or [],
    )


def _holiday_dates(calendar) -> list[str] | None:
    if calendar is None:
        return None
    exceptions = _java_items(calendar, "getCalendarExceptions", "getExceptions")
    if exceptions is None:
        return None
    days: set[str] = set()
    for item in exceptions:
        if _call(item, "getWorking") is True:
            continue
        start = iso_date(_call(item, "getFromDate") or _call(item, "getFrom"))
        finish = iso_date(_call(item, "getToDate") or _call(item, "getTo") or start)
        if not start:
            continue
        try:
            cursor = date.fromisoformat(start[:10])
            last = date.fromisoformat((finish or start)[:10])
        except ValueError:
            continue
        while cursor <= last:
            days.add(cursor.isoformat())
            cursor += timedelta(days=1)
    return sorted(days)


def _java_items(source, *methods: str) -> list | None:
    for method in methods:
        getter = getattr(source, method, None)
        if getter is None:
            continue
        try:
            raw = getter()
        except Exception:  # noqa: BLE001 - optional MPXJ calendar API
            continue
        if raw is None:
            return []
        try:
            return list(raw)
        except TypeError:
            items: list = []
            try:
                iterator = raw.iterator()
                while iterator.hasNext():
                    items.append(iterator.next())
                return items
            except Exception:  # noqa: BLE001
                continue
    return None


def _call(source, method: str):
    getter = getattr(source, method, None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:  # noqa: BLE001
        return None


def iso_date(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text and len(text) >= 10:
        return text[:10]
    return text[:10] if len(text) >= 10 else text


def _successor_task(relation):
    for method in ("getSuccessorTask", "getTargetTask", "getSuccessor"):
        value = _call(relation, method)
        if value is not None:
            return value
    return None


def _relation_type(relation) -> str:
    raw = _call(relation, "getType")
    label = str(raw or "FINISH_START").upper().replace("-", "_")
    mapping = {
        "FINISH_START": "FS",
        "START_START": "SS",
        "FINISH_FINISH": "FF",
        "START_FINISH": "SF",
        "FS": "FS",
        "SS": "SS",
        "FF": "FF",
        "SF": "SF",
    }
    return mapping.get(label, "FS")


def _lag_days(relation, calendar) -> int:
    lag = _call(relation, "getLag")
    hours = duration_hours(lag, calendar)
    if hours is None:
        return 0
    return int(round(hours / 8.0))


def _slack_days(task, calendar) -> float | None:
    slack = _task_value(task, "getTotalSlack")
    hours = duration_hours(slack, calendar)
    if hours is None:
        return None
    return hours / 8.0


def _critical(task) -> bool | None:
    value = _task_value(task, "getCritical")
    if value is None:
        return None
    return bool(value)


def _calendar_name(task, project_calendar) -> str | None:
    calendar = _task_value(task, "getCalendar") or project_calendar
    if calendar is None:
        return None
    name = _call(calendar, "getName")
    text = str(name).strip() if name is not None else ""
    return text or None


def duration_hours(duration, calendar=None) -> float | None:
    if duration is None:
        return None
    try:
        from org.mpxj import TimeUnit
    except Exception:  # noqa: BLE001 - unit tests may call without JVM
        return None
    units = duration.getUnits()
    amount = float(duration.getDuration())
    if units in (TimeUnit.HOURS, TimeUnit.ELAPSED_HOURS):
        return amount
    if units in (TimeUnit.MINUTES, TimeUnit.ELAPSED_MINUTES):
        return amount / 60.0
    if calendar is None:
        return None
    try:
        converted = duration.convertUnits(TimeUnit.HOURS, calendar)
        return float(converted.getDuration())
    except Exception:  # noqa: BLE001 - missing calendar means insufficient data
        return None


def _percent(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _wbs_code(task) -> str | None:
    codes: list[str] = []
    for raw in (_task_value(task, "getWBS"), _task_value(task, "getOutlineNumber")):
        text = str(raw).strip() if raw is not None else ""
        if text and text.lower() != "none":
            codes.append(text)
    for text in codes:
        if _is_project_or_phase_wbs(text):
            return text
    return codes[0] if codes else None


def _task_value(task, method: str):
    getter = getattr(task, method, None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:  # noqa: BLE001 - optional MPXJ field
        return None


def _is_project_or_phase_wbs(value: str) -> bool:
    text = value.strip()
    if text == "1":
        return True
    parts = text.split(".")
    return len(parts) == 2 and parts[0] == "1" and parts[1].isdigit()


def _first_text(*values) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _text_field(task, index: int) -> str | None:
    try:
        from java.lang import Integer

        raw = task.getText(Integer(index))
    except Exception:  # noqa: BLE001 - text field is optional
        return None
    if not raw:
        return None
    text = str(raw).strip()
    return text or None


def _gate_field(project):
    try:
        fields = project.getCustomFields()
    except Exception:  # noqa: BLE001 - custom fields are optional
        return None
    if fields is None:
        return None
    try:
        iterable = list(fields)
    except TypeError:
        iterable = []
        try:
            iterator = fields.iterator()
            while iterator.hasNext():
                iterable.append(iterator.next())
        except Exception:  # noqa: BLE001
            return None
    for field in iterable:
        try:
            alias = str(field.getAlias() or "").strip().lower()
        except Exception:  # noqa: BLE001
            continue
        if alias == "gate":
            try:
                return field.getFieldType()
            except Exception:  # noqa: BLE001
                return None
    return None


def _gate_value(task, gate_field) -> str | None:
    if gate_field is None:
        return None
    try:
        raw = task.get(gate_field)
    except Exception:  # noqa: BLE001
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _assignment(assignment, calendar) -> PlanAssignmentData | None:
    resource = assignment.getResource()
    name = resource.getName() if resource is not None else None
    if not name:
        return None
    resource_id = None
    if resource is not None and resource.getUniqueID() is not None:
        resource_id = int(resource.getUniqueID())
    return PlanAssignmentData(
        resource_id=resource_id,
        resource_name=str(name),
        planned_work_hours=duration_hours(assignment.getWork(), calendar),
        actual_work_hours=duration_hours(assignment.getActualWork(), calendar),
    )


def _phase(task: PlanTaskData) -> PlanPhaseData:
    return PlanPhaseData(
        id=task.id,
        name=task.name,
        scheduled_start=task.scheduled_start,
        scheduled_finish=task.scheduled_finish,
        baseline_start=task.baseline_start,
        baseline_finish=task.baseline_finish,
        actual_start=task.actual_start,
        percent_complete=task.percent_complete,
    )

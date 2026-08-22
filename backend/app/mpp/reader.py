from __future__ import annotations

import tempfile
from pathlib import Path

from app.errors import AppError
from app.models import PlanTaskData, ProjectPlanData
from app.mpp.bridge import ensure_jvm


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

    props = project.getProjectProperties()
    name = str(props.getProjectTitle() or Path(path).stem)
    status_date = _iso(props.getStatusDate())
    tasks: list[PlanTaskData] = []
    has_actuals = False
    for task in project.getTasks():
        task_name = task.getName()
        if not task_name:
            continue
        unique_id = int(task.getUniqueID())
        baseline_start = _iso(task.getBaselineStart())
        baseline_finish = _iso(task.getBaselineFinish())
        actual_start = _iso(task.getActualStart())
        actual_finish = _iso(task.getActualFinish())
        percent = float(task.getPercentageComplete() or 0)
        if actual_start or actual_finish or percent > 0:
            has_actuals = True
        predecessors = []
        for relation in task.getPredecessors():
            pred = relation.getPredecessorTask()
            if pred is not None and pred.getUniqueID() is not None:
                predecessors.append(int(pred.getUniqueID()))
        set_name = None
        try:
            from java.lang import Integer

            raw = task.getText(Integer(1))
            if raw:
                set_name = str(raw)
        except Exception:  # noqa: BLE001 - text field is optional
            set_name = None
        tasks.append(
            PlanTaskData(
                id=unique_id,
                name=str(task_name),
                outline_level=int(task.getOutlineLevel() or 1),
                is_summary=bool(task.getSummary()),
                is_milestone=bool(task.getMilestone()),
                set_name=set_name,
                baseline_start=baseline_start,
                baseline_finish=baseline_finish,
                actual_start=actual_start,
                actual_finish=actual_finish,
                percent_complete=percent,
                predecessor_ids=predecessors,
                comparison_available=bool(baseline_start or baseline_finish),
            )
        )
    return ProjectPlanData(
        name=name,
        status_date=status_date,
        has_actuals=has_actuals,
        planned_only=not has_actuals,
        tasks=tasks,
    )


def _iso(value) -> str | None:
    if value is None:
        return None
    return str(value)

from __future__ import annotations

import tempfile
from pathlib import Path

from app.errors import AppError
from app.models import GeneratedPlan
from app.mpp.bridge import ensure_jvm


def write_generated_plan(plan: GeneratedPlan) -> bytes:
    """Write Microsoft Project XML (MSPDI). Current MPXJ cannot write binary .mpp."""
    ensure_jvm()
    from java.lang import Integer
    from java.math import BigDecimal
    from org.mpxj import Duration, ProjectFile, Relation, RelationType, TimeUnit
    from org.mpxj.writer import FileFormat, UniversalProjectWriter

    project = ProjectFile()
    project.getProjectProperties().setProjectTitle(plan.name)
    created = {}
    for item in plan.tasks:
        task = project.addTask()
        task.setName(item.name)
        task.setOutlineLevel(Integer(item.outline_level))
        task.setMilestone(item.is_milestone)
        if item.is_milestone:
            task.setDuration(Duration.getInstance(0, TimeUnit.DAYS))
        elif not item.is_summary:
            task.setDuration(Duration.getInstance(1, TimeUnit.DAYS))
        task.setPercentageComplete(BigDecimal.ZERO)
        task.setWork(Duration.getInstance(0, TimeUnit.HOURS))
        task.setActualWork(Duration.getInstance(0, TimeUnit.HOURS))
        if item.set_name:
            task.setText(Integer(1), item.set_name)
        created[item.id] = task
    for item in plan.tasks:
        task = created[item.id]
        for pred_id in item.predecessor_ids:
            predecessor = created.get(pred_id)
            if predecessor is None:
                continue
            task.addPredecessor(
                Relation.Builder().predecessorTask(predecessor).type(RelationType.FINISH_START)
            )
    tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
    tmp.close()
    try:
        UniversalProjectWriter(FileFormat.MSPDI).write(project, tmp.name)
        return Path(tmp.name).read_bytes()
    except Exception as exc:  # noqa: BLE001
        raise AppError(500, "MPP_WRITE_FAILED", "The project file could not be generated") from exc
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass

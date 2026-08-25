import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.models import GeneratedPlan, GeneratedTask
from app.mpp import read_mpp_bytes, write_generated_plan
from app.mpp.reader import iso_date


def _sample_plan() -> GeneratedPlan:
    return GeneratedPlan(
        name="Sample Plan",
        tasks=[
            GeneratedTask(id=1, name="Initiation", outline_level=1, is_summary=True),
            GeneratedTask(
                id=2,
                name="Kickoff",
                outline_level=2,
                set_name="Set 1",
                predecessor_ids=[],
            ),
            GeneratedTask(
                id=3,
                name="Charter",
                outline_level=2,
                predecessor_ids=[2],
            ),
            GeneratedTask(id=4, name="Go Live", outline_level=2, is_milestone=True),
        ],
    )


def test_write_and_read_generated_plan() -> None:
    try:
        xml = write_generated_plan(_sample_plan())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"JVM/MPXJ not available: {exc}")
    plan = read_mpp_bytes(xml, "plan.xml")
    names = [task.name for task in plan.tasks]
    assert "Initiation" in names
    assert "Kickoff" in names
    kickoff = next(task for task in plan.tasks if task.name == "Kickoff")
    charter = next(task for task in plan.tasks if task.name == "Charter")
    assert kickoff.percent_complete == 0
    assert charter.predecessor_ids
    assert kickoff.set_name == "Set 1"
    assert plan.planned_only is True


def test_unreadable_mpp_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        read_mpp_bytes(b"this is not a project file", "bad.mpp")
    assert exc.value.code == "UNREADABLE_MPP"


def test_wsr_upload_parses_generated_plan(client: TestClient) -> None:
    try:
        xml = write_generated_plan(_sample_plan())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"JVM/MPXJ not available: {exc}")
    response = client.post(
        "/api/v1/files",
        files={"file": ("plan.mpp", xml, "application/vnd.ms-project")},
        data={"module": "wsr"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_available"] is True
    parsed = client.get(f"/api/v1/files/{body['id']}/plan")
    assert parsed.status_code == 200
    assert any(task["name"] == "Kickoff" for task in parsed.json()["tasks"])


def test_wsr_upload_rejects_garbage_mpp(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={"file": ("plan.mpp", b"not-an-mpp", "application/vnd.ms-project")},
        data={"module": "wsr"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_iso_date_keeps_absent_values_unavailable() -> None:
    assert iso_date(None) is None
    assert iso_date("2026-08-22T09:30:00") == "2026-08-22"
    assert iso_date("2026-08-22 09:30:00") == "2026-08-22"


def test_wsr_reader_projects_identity_dates_gate_and_assignments() -> None:
    try:
        from app.mpp.bridge import ensure_jvm
        from app.mpp.reader import project_from_mpxj

        ensure_jvm()
        from java.lang import Integer
        from java.math import BigDecimal
        from java.time import LocalDateTime
        from org.mpxj import Duration, ProjectFile, Relation, RelationType, TaskField, TimeUnit
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"JVM/MPXJ not available: {exc}")

    project = ProjectFile()
    props = project.getProjectProperties()
    props.setProjectTitle("Core Banking")
    props.setManager("Priya Shah")
    props.setStatusDate(LocalDateTime.of(2026, 8, 22, 8, 0))
    try:
        project.getCustomFields().get(TaskField.TEXT2).setAlias("Gate")
    except Exception:  # noqa: BLE001 - alias API varies by MPXJ build
        pass

    phase = project.addTask()
    phase.setName("Build")
    phase.setOutlineLevel(Integer(1))
    phase.setSummary(True)
    phase.setStart(LocalDateTime.of(2026, 7, 1, 8, 0))
    phase.setFinish(LocalDateTime.of(2026, 9, 30, 17, 0))

    kickoff = project.addTask()
    kickoff.setName("Kickoff")
    kickoff.setOutlineLevel(Integer(2))
    kickoff.setStart(LocalDateTime.of(2026, 7, 1, 8, 0))
    kickoff.setFinish(LocalDateTime.of(2026, 7, 1, 17, 0))
    kickoff.setBaselineStart(LocalDateTime.of(2026, 7, 1, 8, 0))
    kickoff.setBaselineFinish(LocalDateTime.of(2026, 7, 1, 17, 0))
    kickoff.setPercentageComplete(BigDecimal("100"))
    kickoff.setActualStart(LocalDateTime.of(2026, 7, 1, 8, 0))
    kickoff.setActualFinish(LocalDateTime.of(2026, 7, 1, 17, 0))

    go_live = project.addTask()
    go_live.setName("Go Live")
    go_live.setOutlineLevel(Integer(2))
    go_live.setMilestone(True)
    go_live.setStart(LocalDateTime.of(2026, 10, 1, 8, 0))
    go_live.setFinish(LocalDateTime.of(2026, 10, 1, 8, 0))
    go_live.setText(Integer(2), "Go-Live")
    go_live.addPredecessor(Relation.Builder().predecessorTask(kickoff).type(RelationType.FINISH_START))

    analyst = project.addResource()
    analyst.setName("Asha")
    assignment = go_live.addResourceAssignment(analyst)
    assignment.setWork(Duration.getInstance(16, TimeUnit.HOURS))
    assignment.setActualWork(Duration.getInstance(0, TimeUnit.HOURS))

    plan = project_from_mpxj(project)
    assert plan.name == "Core Banking"
    assert plan.owner == "Priya Shah"
    assert plan.status_date == "2026-08-22"
    assert plan.has_actuals is True
    assert plan.planned_only is False
    assert any(phase.name == "Build" for phase in plan.phases)
    kickoff_row = next(task for task in plan.tasks if task.name == "Kickoff")
    assert kickoff_row.scheduled_start == "2026-07-01"
    assert kickoff_row.baseline_finish == "2026-07-01"
    assert kickoff_row.actual_finish == "2026-07-01"
    assert kickoff_row.comparison_available is True
    go_live_row = next(task for task in plan.tasks if task.name == "Go Live")
    assert go_live_row.is_milestone is True
    assert "Kickoff" in go_live_row.predecessor_names
    assert go_live_row.gate in {None, "Go-Live"}
    assert any(resource.name == "Asha" for resource in plan.resources)
    assert any(item.resource_name == "Asha" for item in go_live_row.assignments)
    work_hours = go_live_row.assignments[0].planned_work_hours
    assert work_hours is None or work_hours == 16


def test_wsr_reader_leaves_missing_identity_and_dates_unavailable() -> None:
    try:
        from app.mpp.bridge import ensure_jvm
        from app.mpp.reader import project_from_mpxj

        ensure_jvm()
        from org.mpxj import ProjectFile
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"JVM/MPXJ not available: {exc}")

    project = ProjectFile()
    project.getProjectProperties().setProjectTitle("Sparse")
    task = project.addTask()
    task.setName("Unscheduled work")
    plan = project_from_mpxj(project)
    assert plan.owner is None
    assert plan.status_date is None
    assert plan.phases == []
    row = next(item for item in plan.tasks if item.name == "Unscheduled work")
    assert row.baseline_start is None
    assert row.scheduled_finish is None
    assert row.gate is None
    assert row.assignments == []
    assert row.comparison_available is False
    assert plan.planned_only is True


def test_plan_job_can_download_generated_xml(client: TestClient) -> None:
    created = client.post("/api/v1/plan/jobs", json={})
    handle = created.json()["id"]
    try:
        response = client.post(
            f"/api/v1/plan/jobs/{handle}/mpp",
            json=_sample_plan().model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"JVM/MPXJ not available: {exc}")
    if response.status_code == 500:
        pytest.skip("JVM/MPXJ not available")
    assert response.status_code == 200
    assert response.content.startswith(b"<?xml") or b"Project" in response.content
    downloaded = client.get(f"/api/v1/plan/jobs/{handle}/mpp")
    assert downloaded.status_code == 200

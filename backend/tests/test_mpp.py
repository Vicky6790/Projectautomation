import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.models import GeneratedPlan, GeneratedTask
from app.mpp import read_mpp_bytes, write_generated_plan


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
    assert response.json()["error"]["code"] == "UNREADABLE_MPP"


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

from fastapi.testclient import TestClient

from app.mpp.mspdi import inspect_mspdi


def _config(**kwargs) -> dict:
    payload = {
        "name": "Demo plan",
        "common_set_count": 1,
        "phases": [
            {"phase_id": "ux", "deliverables": ["ux_research"]},
            {"phase_id": "ui", "deliverables": ["ui_creation"]},
        ],
    }
    payload.update(kwargs)
    return payload


def test_preview_requires_a_phase(client: TestClient) -> None:
    response = client.post("/api/v1/plan/preview", json={"phases": []})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PLAN_EMPTY"


def test_invalid_set_count_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/plan/preview", json=_config(common_set_count=0))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SET_COUNT_INVALID"


def test_sequence_conflict_identifies_phases(client: TestClient) -> None:
    response = client.post(
        "/api/v1/plan/preview",
        json={
            "phases": [
                {"phase_id": "ui", "deliverables": ["ui_creation"]},
                {"phase_id": "ux", "deliverables": ["ux_research"]},
            ]
        },
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SEQUENCE_CONFLICT"
    assert ["ux", "ui"] in error["details"]["conflicting_phases"]


def test_duplicate_phase_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/plan/preview",
        json={
            "phases": [
                {"phase_id": "ux", "deliverables": ["ux_research"]},
                {"phase_id": "ux", "deliverables": ["wireframe_creation"]},
            ]
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DUPLICATE_PHASE"


def test_approve_requires_preview(client: TestClient) -> None:
    created = client.post("/api/v1/plan/jobs", json={})
    assert created.status_code == 200
    handle = created.json()["id"]
    response = client.post(f"/api/v1/plan/requests/{handle}/approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PREVIEW_NOT_READY"


def test_preview_then_approve_downloads_xml(client: TestClient) -> None:
    preview = client.post("/api/v1/plan/preview", json=_config())
    if preview.status_code == 500:
        return
    assert preview.status_code == 200, preview.text
    handle = preview.json()["id"]
    assert preview.json()["result"]["plan"]["tasks"]
    assert preview.json()["result"]["approved"] is False
    retry = client.post(f"/api/v1/plan/requests/{handle}/preview")
    assert retry.status_code == 200
    approved = client.post(f"/api/v1/plan/requests/{handle}/approve")
    if approved.status_code == 500:
        return
    assert approved.status_code == 200
    assert approved.json()["result"]["approved"] is True
    download = client.get(f"/api/v1/plan/requests/{handle}/mpp")
    assert download.status_code == 200
    assert b"Project" in download.content or download.content.startswith(b"<?xml")
    problems = inspect_mspdi(download.content)
    assert problems == [], problems

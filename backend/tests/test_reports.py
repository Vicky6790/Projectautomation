from fastapi.testclient import TestClient

from tests.helpers import docx_bytes


def _complete_sow(client: TestClient) -> str:
    uploaded = client.post(
        "/api/v1/files",
        files={
            "file": (
                "sow.docx",
                docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"module": "sow"},
    )
    handle = uploaded.json()["id"]
    client.post("/api/v1/sow/jobs", json={"file_id": handle})
    from app.storage import store

    store.set_status(
        handle,
        "succeeded",
        result={"risks": ["Scope may grow without change control"], "gray_areas": []},
    )
    return handle


def test_export_refuses_incomplete_job(client: TestClient) -> None:
    uploaded = client.post(
        "/api/v1/files",
        files={
            "file": (
                "sow.docx",
                docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"module": "sow"},
    )
    handle = uploaded.json()["id"]
    client.post("/api/v1/sow/jobs", json={"file_id": handle})
    response = client.get(f"/api/v1/sow/jobs/{handle}/report")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EXPORT_NOT_READY"


def test_export_includes_empty_sow_sections(client: TestClient) -> None:
    handle = _complete_sow(client)
    response = client.get(f"/api/v1/sow/requests/{handle}/report")
    assert response.status_code == 200
    text = response.text
    assert "Gray areas" in text
    assert "Empty" in text
    assert "Scope may grow" in text
    assert "attachment;" in response.headers["content-disposition"]


def test_plan_has_no_document_report(client: TestClient) -> None:
    created = client.post("/api/v1/plan/jobs", json={})
    handle = created.json()["id"]
    from app.storage import store

    store.set_status(handle, "succeeded", result={"name": "preview"})
    response = client.get(f"/api/v1/plan/jobs/{handle}/report")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REPORT_NOT_SUPPORTED"

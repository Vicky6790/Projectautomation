from fastapi.testclient import TestClient

from tests.helpers import docx_bytes


def _upload(client: TestClient, payload: bytes | None = None) -> tuple[str, bytes]:
    content = payload if payload is not None else docx_bytes()
    response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "sow.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"module": "sow"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"], content


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_required"] is False


def test_upload_download_roundtrip(client: TestClient) -> None:
    payload = docx_bytes()
    file_id, content = _upload(client, payload)
    meta = client.get(f"/api/v1/files/{file_id}")
    assert meta.status_code == 200
    downloaded = client.get(f"/api/v1/files/{file_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == content


def test_sow_start_status_retry_contract(client: TestClient) -> None:
    file_id, _ = _upload(client)
    started = client.post("/api/v1/sow/jobs", json={"file_id": file_id})
    assert started.status_code == 200
    job = started.json()
    assert job["module"] == "sow"
    assert job["status"] == "queued"
    assert job["error"] is None

    status = client.get(f"/api/v1/sow/jobs/{job['id']}")
    assert status.status_code == 200
    assert status.json()["id"] == job["id"]

    retry = client.post(f"/api/v1/sow/jobs/{job['id']}/retry")
    assert retry.status_code == 409
    error = retry.json()["error"]
    assert error["code"] == "RETRY_NOT_ALLOWED"
    assert error["retryable"] is False


def test_all_modules_have_start_status_retry(client: TestClient) -> None:
    sow_id, _ = _upload(client)
    started = client.post("/api/v1/sow/jobs", json={"file_id": sow_id})
    assert started.status_code == 200
    assert started.json()["id"] == sow_id
    plan = client.post("/api/v1/plan/jobs", json={})
    assert plan.status_code == 200
    assert client.get(f"/api/v1/plan/jobs/{plan.json()['id']}").status_code == 200


def test_missing_file_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/files/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "FILE_NOT_FOUND"
    assert "retryable" in error


def test_upload_rejects_oversize_file(client: TestClient, monkeypatch) -> None:
    from app.ingestion import policy

    monkeypatch.setattr(
        policy,
        "SOW_POLICY",
        policy.UploadPolicy(
            kind="sow",
            extensions=frozenset({".pdf", ".docx"}),
            max_bytes=8,
            format_label="PDF (.pdf) and Word (.docx)",
        ),
    )
    response = client.post(
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
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"

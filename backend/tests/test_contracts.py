from fastapi.testclient import TestClient


def _upload(client: TestClient) -> str:
    response = client.post(
        "/api/v1/files",
        files={"file": ("sow.txt", b"statement of work", "text/plain")},
        data={"module": "sow"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_required"] is False


def test_upload_download_roundtrip(client: TestClient) -> None:
    file_id = _upload(client)
    meta = client.get(f"/api/v1/files/{file_id}")
    assert meta.status_code == 200
    downloaded = client.get(f"/api/v1/files/{file_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"statement of work"


def test_sow_start_status_retry_contract(client: TestClient) -> None:
    file_id = _upload(client)
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
    file_id = _upload(client)
    for module in ("sow", "wsr", "retrospective", "plan"):
        started = client.post(f"/api/v1/{module}/jobs", json={"file_id": file_id})
        assert started.status_code == 200, module
        job_id = started.json()["id"]
        assert client.get(f"/api/v1/{module}/jobs/{job_id}").status_code == 200
        retry = client.post(f"/api/v1/{module}/jobs/{job_id}/retry")
        assert retry.status_code == 409


def test_missing_file_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/files/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "FILE_NOT_FOUND"
    assert "retryable" in error

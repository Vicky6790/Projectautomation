from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import docx_bytes


def _upload(client: TestClient) -> str:
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
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body.get("data_dir")


def test_start_is_idempotent_per_handle(client: TestClient) -> None:
    file_id = _upload(client)
    first = client.post("/api/v1/sow/jobs", json={"file_id": file_id})
    second = client.post("/api/v1/sow/jobs", json={"file_id": file_id})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"] == file_id
    assert first.json()["request_handle"] == file_id


def test_retry_after_failure_requeues_same_handle(client: TestClient) -> None:
    from app.storage import store

    file_id = _upload(client)
    started = client.post("/api/v1/sow/jobs", json={"file_id": file_id})
    assert started.status_code == 200
    store.set_status(
        file_id,
        "failed",
        error={"code": "AI_FAILED", "message": "boom", "retryable": True},
    )
    retried = client.post(f"/api/v1/sow/jobs/{file_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] == file_id
    assert retried.json()["status"] == "queued"
    assert retried.json()["error"] is None


def test_handles_are_isolated(client: TestClient) -> None:
    first = _upload(client)
    second = _upload(client)
    assert first != second
    client.post("/api/v1/sow/jobs", json={"file_id": first})
    client.post("/api/v1/sow/jobs", json={"file_id": second})
    from app.storage import store

    store.set_status(first, "succeeded", result={"ok": True})
    assert store.get_job(second).status == "queued"
    assert store.get_job(first).status == "succeeded"


def test_expired_handles_are_removed(client: TestClient, monkeypatch) -> None:
    from app.config import settings
    from app.storage import store

    monkeypatch.setattr(settings, "request_ttl_hours", 1)
    file_id = _upload(client)
    record, _ = store.get_file(file_id)
    record.last_accessed_at = datetime.now(UTC) - timedelta(hours=2)
    store._write_file(record)
    removed = store.purge_expired()
    assert removed >= 1
    missing = client.get(f"/api/v1/files/{file_id}")
    assert missing.status_code == 404

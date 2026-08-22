from pathlib import Path

from fastapi.testclient import TestClient

from app import config, storage
from app.access import access
from app.main import create_app
from app.storage import LocalStore
from tests.helpers import docx_bytes


def _auth_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config.settings, "auth_mode", "required")
    monkeypatch.setattr(config.settings, "auth_bootstrap_user", "admin")
    monkeypatch.setattr(config.settings, "auth_bootstrap_password", "secret")
    store = LocalStore(tmp_path)
    monkeypatch.setattr(storage, "store", store)
    from app.routers import files, jobs

    monkeypatch.setattr(files, "store", store)
    monkeypatch.setattr(jobs, "store", store)
    access.bootstrap()
    return TestClient(create_app())


def _sow_file() -> dict:
    return {
        "file": (
            "sow.docx",
            docx_bytes("The vendor shall deliver a portal."),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }


def test_health_is_public_when_auth_required(tmp_path: Path, monkeypatch) -> None:
    client = _auth_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["auth_required"] is True


def test_module_route_requires_session(tmp_path: Path, monkeypatch) -> None:
    client = _auth_client(tmp_path, monkeypatch)
    response = client.get("/api/v1/plan/library")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_wrong_password_does_not_reveal_identity(tmp_path: Path, monkeypatch) -> None:
    client = _auth_client(tmp_path, monkeypatch)
    missing = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    wrong = client.post("/api/v1/auth/login", json={"username": "admin", "password": "x"})
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["error"]["message"] == wrong.json()["error"]["message"]
    assert missing.json()["error"]["code"] == "AUTH_FAILED"


def test_operator_cannot_read_another_operator_handle(tmp_path: Path, monkeypatch) -> None:
    app_client = _auth_client(tmp_path, monkeypatch)
    login = app_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert login.status_code == 200, login.text
    created = app_client.post(
        "/api/v1/auth/users",
        json={"username": "operator", "password": "operator-secret", "role": "operator"},
    )
    assert created.status_code == 200, created.text

    other = TestClient(app_client.app)
    signed = other.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "operator-secret"},
    )
    assert signed.status_code == 200, signed.text
    upload = other.post("/api/v1/sow/uploads", files=_sow_file())
    assert upload.status_code == 200, upload.text
    handle = upload.json()["id"]

    blocked = app_client.get(f"/api/v1/files/{handle}")
    assert blocked.status_code == 404
    assert blocked.json()["error"]["code"] == "FILE_NOT_FOUND"
    job = app_client.get(f"/api/v1/sow/requests/{handle}")
    assert job.status_code == 404
    assert job.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_operator_cannot_call_admin_routes(tmp_path: Path, monkeypatch) -> None:
    app_client = _auth_client(tmp_path, monkeypatch)
    admin = app_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert admin.status_code == 200
    created = app_client.post(
        "/api/v1/auth/users",
        json={"username": "operator", "password": "operator-secret", "role": "operator"},
    )
    assert created.status_code == 200
    operator = TestClient(app_client.app)
    operator.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "operator-secret"},
    )
    listed = operator.get("/api/v1/auth/users")
    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_idle_session_requires_sign_in_again(tmp_path: Path, monkeypatch) -> None:
    import json
    from datetime import UTC, datetime, timedelta

    client = _auth_client(tmp_path, monkeypatch)
    signed = client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert signed.status_code == 200
    path = tmp_path / "sessions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stale = (datetime.now(UTC) - timedelta(hours=9)).isoformat()
    for session in payload.get("sessions", []):
        session["last_seen"] = stale
    path.write_text(json.dumps(payload), encoding="utf-8")
    denied = client.get("/api/v1/plan/library")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "AUTH_REQUIRED"


def test_disabled_operator_session_is_rejected(tmp_path: Path, monkeypatch) -> None:
    app_client = _auth_client(tmp_path, monkeypatch)
    admin = app_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert admin.status_code == 200
    created = app_client.post(
        "/api/v1/auth/users",
        json={"username": "operator", "password": "operator-secret", "role": "operator"},
    )
    assert created.status_code == 200
    operator_id = created.json()["id"]
    operator = TestClient(app_client.app)
    signed = operator.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "operator-secret"},
    )
    assert signed.status_code == 200
    disabled = app_client.post(f"/api/v1/auth/users/{operator_id}/disable")
    assert disabled.status_code == 200
    denied = operator.get("/api/v1/plan/library")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "AUTH_REQUIRED"

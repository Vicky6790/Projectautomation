from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, storage
from app.main import create_app
from app.storage import LocalStore


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config.settings, "auth_mode", "disabled")
    monkeypatch.setattr(config.settings, "ai_stub", True)
    store = LocalStore(tmp_path)
    monkeypatch.setattr(storage, "store", store)
    from app.routers import files, jobs

    monkeypatch.setattr(files, "store", store)
    monkeypatch.setattr(jobs, "store", store)
    return TestClient(create_app())

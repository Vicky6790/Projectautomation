from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import create_app


def test_cors_regex_allows_vercel_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config.settings, "cors_origins", "http://localhost:5173")
    monkeypatch.setattr(config.settings, "cors_origin_regex", r"https://.*\.vercel\.app")
    client = TestClient(create_app())
    origin = "https://projectautomation-git-preview.vercel.app"
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_empty_cors_regex_does_not_allow_unknown_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config.settings, "cors_origins", "http://localhost:5173")
    monkeypatch.setattr(config.settings, "cors_origin_regex", "")
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"

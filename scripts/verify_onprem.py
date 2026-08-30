"""Verify the on-premise Compose overlay: health, storage, auth, SPA, API proxy."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from client_session import DEFAULT_BASE, ensure_session

PAGES = ("/sow", "/plan", "/wsr", "/delay-mapping", "/retrospective")


def _port_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    base = os.environ.get("APP_BASE_URL", DEFAULT_BASE)
    client = httpx.Client(base_url=base, timeout=60)

    health = client.get("/health")
    print("health", health.status_code, health.text[:160])
    if health.status_code != 200:
        return 1
    body = health.json()
    if body.get("status") != "ok":
        print("health payload unexpected", body)
        return 1
    if not body.get("auth_required"):
        print("on-prem overlay must report auth_required=true")
        return 1

    ready = client.get("/ready")
    print("ready", ready.status_code, ready.text[:200])
    if ready.status_code != 200:
        print("API is not ready; set AUTH_BOOTSTRAP_PASSWORD and confirm DATA_DIR is writable")
        return 1

    denied = client.get("/api/v1/plan/library")
    print("unauthenticated library", denied.status_code, denied.json().get("error", {}).get("code"))
    if denied.status_code != 401 or denied.json().get("error", {}).get("code") != "AUTH_REQUIRED":
        print(denied.text)
        return 1

    try:
        ensure_session(client, body)
    except RuntimeError as exc:
        print(exc)
        return 1

    me = client.get("/api/v1/auth/me")
    print("me", me.status_code, me.text[:160])
    if me.status_code != 200 or me.json().get("role") != "admin":
        print("bootstrap operator is not an administrator")
        return 1

    library = client.get("/api/v1/plan/library")
    print("library", library.status_code)
    if library.status_code != 200:
        print(library.text)
        return 1

    created = client.post(
        "/api/v1/auth/users",
        json={"username": "onprem-operator", "password": "operator-secret", "role": "operator"},
    )
    print("create operator", created.status_code)
    if created.status_code not in {200, 409}:
        print(created.text)
        return 1

    operator = httpx.Client(base_url=base, timeout=60)
    signed = operator.post(
        "/api/v1/auth/login",
        json={"username": "onprem-operator", "password": "operator-secret"},
    )
    if signed.status_code != 200:
        print("operator sign-in failed", signed.text)
        return 1
    preview = operator.post(
        "/api/v1/plan/preview",
        json={
            "name": "On-prem isolation",
            "common_set_count": 1,
            "phases": [{"phase_id": "ux", "deliverables": ["ux_research"]}],
        },
    )
    print("operator preview", preview.status_code)
    if preview.status_code != 200:
        print(preview.text)
        return 1
    handle = preview.json()["id"]
    blocked = client.get(f"/api/v1/plan/requests/{handle}")
    print(
        "admin reads operator handle",
        blocked.status_code,
        blocked.json().get("error", {}).get("code"),
    )
    if blocked.status_code != 404:
        print(blocked.text)
        return 1

    for path in PAGES:
        page = client.get(path)
        print("page", path, page.status_code, page.headers.get("content-type"))
        if page.status_code != 200 or "html" not in (page.headers.get("content-type") or ""):
            print(page.text[:200])
            return 1

    if not _port_closed(8000):
        print("API port 8000 is published on the host; Compose should keep it internal")
        return 1

    data_dir = Path(os.environ.get("ONPREM_DATA_DIR", "./onprem-data"))
    if data_dir.exists():
        print("host data dir present", data_dir.resolve())
    else:
        print("host data dir not created yet (first request should create it):", data_dir)

    print("On-prem Compose check via client origin: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

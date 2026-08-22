"""Verify Plan Generator configure → preview → approve → download through the Client App proxy."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.mpp.mspdi import inspect_mspdi  # noqa: E402

BASE = "http://localhost:8080"

CONFIG = {
    "name": "Compose E2E Plan",
    "common_set_count": 2,
    "phases": [
        {"phase_id": "discovery", "deliverables": ["discovery_kickoff"]},
        {"phase_id": "ux", "deliverables": ["ux_research", "wireframe_creation"]},
        {"phase_id": "ui", "deliverables": ["ui_creation"]},
    ],
}


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=180)
    health = client.get("/health")
    print("health", health.status_code, health.text[:120])
    if health.status_code != 200:
        return 1

    page = client.get("/plan")
    print("plan page", page.status_code, page.headers.get("content-type"))
    if page.status_code != 200 or "html" not in (page.headers.get("content-type") or ""):
        print(page.text[:200])
        return 1

    library = client.get("/api/v1/plan/library")
    print("library", library.status_code)
    if library.status_code != 200:
        print(library.text)
        return 1
    ids = [phase["id"] for phase in library.json()["phases"]]
    if "ux" not in ids or "ui" not in ids:
        print("library missing expected phases", ids)
        return 1

    empty = client.post("/api/v1/plan/preview", json={"phases": []})
    print("empty", empty.status_code, empty.json().get("error", {}).get("code"))
    if empty.status_code != 400 or empty.json()["error"]["code"] != "PLAN_EMPTY":
        return 1

    conflict = client.post(
        "/api/v1/plan/preview",
        json={
            "phases": [
                {"phase_id": "ui", "deliverables": ["ui_creation"]},
                {"phase_id": "ux", "deliverables": ["ux_research"]},
            ]
        },
    )
    print("conflict", conflict.status_code, conflict.json().get("error", {}).get("code"))
    if conflict.status_code != 409:
        return 1

    preview = client.post("/api/v1/plan/preview", json=CONFIG)
    print("preview", preview.status_code)
    if preview.status_code != 200:
        print(preview.text)
        return 1
    handle = preview.json()["id"]
    result = preview.json()["result"]
    if not result or not result.get("plan", {}).get("tasks"):
        print("preview missing tasks")
        return 1

    retry = client.post(f"/api/v1/plan/requests/{handle}/preview")
    print("retry preview", retry.status_code)
    if retry.status_code != 200:
        print(retry.text)
        return 1

    approved = client.post(f"/api/v1/plan/requests/{handle}/approve")
    print("approve", approved.status_code)
    if approved.status_code != 200:
        print(approved.text)
        return 1
    if not approved.json()["result"].get("mpp_available"):
        print("mpp_available not set")
        return 1

    download = client.get(f"/api/v1/plan/requests/{handle}/mpp")
    print("mpp", download.status_code, download.headers.get("content-type"), len(download.content))
    if download.status_code != 200:
        print(download.text)
        return 1
    xml = download.content
    problems = inspect_mspdi(xml)
    if problems:
        print("mspdi problems", problems)
        root = ET.fromstring(xml)
        print("root", root.tag)
        return 1
    print("Plan Generator E2E via client proxy: OK", handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())

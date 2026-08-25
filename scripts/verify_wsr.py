"""Verify WSR upload → generate → report through the Client App proxy."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_session import ensure_session

BASE = "http://localhost:8080"

SECTIONS = (
    "project_health",
    "facts",
    "client_needs",
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
)

PLAN_CONFIG = {
    "name": "WSR E2E Plan",
    "common_set_count": 1,
    "phases": [
        {"phase_id": "ux", "deliverables": ["ux_research"]},
        {"phase_id": "ui", "deliverables": ["ui_creation"]},
    ],
}


def _mspdi(client: httpx.Client) -> bytes:
    preview = client.post("/api/v1/plan/preview", json=PLAN_CONFIG)
    if preview.status_code != 200:
        raise RuntimeError(f"plan preview failed: {preview.status_code} {preview.text}")
    handle = preview.json()["id"]
    approved = client.post(f"/api/v1/plan/requests/{handle}/approve")
    if approved.status_code != 200:
        raise RuntimeError(f"plan approve failed: {approved.status_code} {approved.text}")
    download = client.get(f"/api/v1/plan/requests/{handle}/mpp")
    if download.status_code != 200:
        raise RuntimeError(f"plan download failed: {download.status_code} {download.text}")
    return download.content


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=180)
    health = client.get("/health")
    print("health", health.status_code, health.text[:120])
    if health.status_code != 200:
        return 1
    try:
        ensure_session(client, health.json())
    except RuntimeError as exc:
        print(exc)
        return 1

    page = client.get("/wsr")
    print("wsr page", page.status_code, page.headers.get("content-type"))
    if page.status_code != 200 or "html" not in (page.headers.get("content-type") or ""):
        print(page.text[:200])
        return 1

    garbage = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", b"not-an-mpp", "application/vnd.ms-project")},
    )
    print("garbage", garbage.status_code, garbage.json().get("error", {}).get("code"))
    if garbage.status_code != 400:
        return 1

    try:
        xml = _mspdi(client)
    except RuntimeError as exc:
        print(exc)
        return 1

    upload = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", xml, "application/vnd.ms-project")},
    )
    print("upload", upload.status_code)
    if upload.status_code != 200:
        print(upload.text)
        return 1
    handle = upload.json()["id"]
    if not upload.json().get("plan_available"):
        print("plan_available not set")
        return 1

    generated = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    print("generate", generated.status_code)
    if generated.status_code != 200:
        print(generated.text)
        return 1
    result = generated.json()["result"] or {}
    for key in SECTIONS:
        if key not in result:
            print("missing section", key)
            return 1
    if not result.get("as_of_date"):
        print("as_of_date missing")
        return 1

    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    print("report", report.status_code, report.headers.get("content-type"))
    if report.status_code != 200:
        print(report.text)
        return 1
    text = report.text
    for heading in (
        "WSR & Insights",
        "Executive Overview",
        "Project Timeline",
        "Phase-Wise Status",
        "Progress to Date",
        "Upcoming Milestones",
        "What We Need From the Bank Team",
        "Issues",
        "Dependencies",
        "Risks & Focus Areas",
        "Management Attention",
        "Decisions Required",
        "Next Seven-Day Priorities",
    ):
        if heading not in text:
            print("report missing heading", heading)
            return 1
    print("WSR E2E via client proxy: OK", handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())

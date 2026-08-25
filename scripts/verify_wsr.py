"""Verify WSR upload → generate → review → report through the Client App proxy."""

from __future__ import annotations

import sys
from pathlib import Path

from io import BytesIO

import httpx
from pypdf import PdfReader

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
    as_of = result["as_of_date"]
    generated_at = result.get("generated_at")

    page_js_ok = _client_bundle_has(
        client,
        (
            "View Source",
            "Download PDF",
            "Overall Progress",
            "Last Signed-Off Milestone",
            "No items identified from the plan",
        ),
    )
    if not page_js_ok:
        return 1

    pending = [
        item
        for key in (
            "client_needs",
            "risks",
            "issues",
            "dependencies",
            "management_attention",
            "decisions_required",
            "next_7_day_priorities",
        )
        for item in (result.get(key) or [])
        if isinstance(item, dict) and item.get("review_status") == "pending"
    ]
    removed_text = None
    edited_text = "Edited insight for WSR E2E"
    if pending:
        blocked = client.get(f"/api/v1/wsr/requests/{handle}/report")
        print("pending report", blocked.status_code, blocked.json().get("error", {}).get("code"))
        if blocked.status_code != 409 or blocked.json().get("error", {}).get("code") != "REVIEW_REQUIRED":
            print(blocked.text)
            return 1
        evidence = client.get(f"/api/v1/wsr/requests/{handle}/items/{pending[0]['id']}/evidence")
        print("evidence", evidence.status_code)
        if evidence.status_code != 200:
            print(evidence.text)
            return 1
        body = evidence.json()
        if "task_or_milestone_name" not in (body.get("evidence_references") or [{}])[0]:
            print("evidence missing source name")
            return 1
        first, *rest = pending
        edited = client.patch(
            f"/api/v1/wsr/requests/{handle}/items/{first['id']}",
            json={"decision": "edited", "content": edited_text},
        )
        if edited.status_code != 200:
            print("edit failed", edited.text)
            return 1
        result = edited.json()["result"] or result
        if rest:
            removed_text = rest[-1].get("content")
            removed = client.patch(
                f"/api/v1/wsr/requests/{handle}/items/{rest[-1]['id']}",
                json={"decision": "removed"},
            )
            if removed.status_code != 200:
                print("remove failed", removed.text)
                return 1
            result = removed.json()["result"] or result
            rest = rest[:-1]
        for item in rest:
            reviewed = client.patch(
                f"/api/v1/wsr/requests/{handle}/items/{item['id']}",
                json={"decision": "kept"},
            )
            if reviewed.status_code != 200:
                print("review failed", item.get("id"), reviewed.status_code, reviewed.text)
                return 1
            result = reviewed.json()["result"] or result
        print("reviewed", len(pending), "items")
    if not result.get("exportable"):
        print("report still not exportable after review")
        return 1

    reopened = client.get(f"/api/v1/wsr/requests/{handle}")
    reopened_result = reopened.json().get("result") or {}
    if reopened_result.get("as_of_date") != as_of or reopened_result.get("generated_at") != generated_at:
        print("as_of or generated_at changed after review")
        return 1

    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    print("report", report.status_code, report.headers.get("content-type"))
    if report.status_code != 200:
        print(report.text)
        return 1
    if not report.content.startswith(b"%PDF"):
        print("report is not a PDF")
        return 1
    if "application/pdf" not in (report.headers.get("content-type") or ""):
        print("unexpected media type")
        return 1
    if ".pdf" not in (report.headers.get("content-disposition") or ""):
        print("missing pdf filename")
        return 1
    text = "\n".join(
        (page.extract_text() or "") for page in PdfReader(BytesIO(report.content)).pages
    )
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
    for label in (
        "Overall Progress",
        "Last Signed-Off Milestone",
        "Work Items Completed",
        "Team Capacity",
        "Next Gate",
        "Go-Live",
        "Phases to Go-Live",
        "People Planned",
        "Resources Deployed",
        "Days to Go-Live",
        as_of,
    ):
        if label not in text:
            print("report missing label", label)
            return 1
    if pending and edited_text not in text:
        print("edited insight missing from PDF")
        return 1
    if removed_text and removed_text in text:
        print("removed insight still in PDF")
        return 1
    print("WSR E2E via client proxy: OK", handle)
    return 0


def _client_bundle_has(client: httpx.Client, needles: tuple[str, ...]) -> bool:
    page = client.get("/wsr")
    html = page.text
    marker = 'src="/assets/'
    start = html.find(marker)
    if start < 0:
        print("client bundle script missing")
        return False
    src_start = start + len('src="')
    src_end = html.find('"', src_start)
    script = client.get(html[src_start:src_end])
    bundle = script.text
    for needle in needles:
        if needle not in bundle:
            print("client bundle missing", needle)
            return False
    print("client bundle review/dashboard strings: OK")
    return True


if __name__ == "__main__":
    sys.exit(main())

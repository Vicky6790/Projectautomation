"""Verify SOW upload → analyze → report through the Client App proxy."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import httpx
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_session import ensure_session

BASE = "http://localhost:8080"

CATEGORIES = (
    "gray_areas",
    "risks",
    "missing_requirements",
    "assumptions",
    "dependencies",
    "clarification_questions",
)


def _sow_bytes() -> bytes:
    document = Document()
    document.add_paragraph(
        "The vendor shall deliver a customer portal in a reasonable time "
        "without defined acceptance criteria."
    )
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _client_bundle(client: httpx.Client) -> str | None:
    page = client.get("/sow")
    html = page.text
    marker = 'src="/assets/'
    start = html.find(marker)
    if start < 0:
        print("client bundle script missing")
        return None
    src_start = start + len('src="')
    src_end = html.find('"', src_start)
    script = client.get(html[src_start:src_end])
    return script.text


def _client_bundle_has(client: httpx.Client, needles: tuple[str, ...]) -> bool:
    bundle = _client_bundle(client)
    if bundle is None:
        return False
    for needle in needles:
        if needle not in bundle:
            print("client bundle missing", needle)
            return False
    print("client bundle dashboard strings: OK")
    return True


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=120)
    health = client.get("/health")
    print("health", health.status_code, health.text[:120])
    if health.status_code != 200:
        return 1
    try:
        ensure_session(client, health.json())
    except RuntimeError as exc:
        print(exc)
        return 1

    page = client.get("/sow")
    print("sow page", page.status_code, page.headers.get("content-type"))
    if page.status_code != 200 or "html" not in (page.headers.get("content-type") or ""):
        print(page.text[:200])
        return 1

    if not _client_bundle_has(
        client,
        (
            "Start analysis",
            "Download analysis report",
            "Analysis summary",
            "No findings were identified.",
            "AI recommendation",
            "Processed pages",
        ),
    ):
        return 1

    upload = client.post(
        "/api/v1/sow/uploads",
        files={
            "file": (
                "sow.docx",
                _sow_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    print("upload", upload.status_code)
    if upload.status_code != 200:
        print(upload.text)
        return 1
    handle = upload.json()["id"]
    analyzed = client.post(f"/api/v1/sow/requests/{handle}/analyze")
    print("analyze", analyzed.status_code)
    if analyzed.status_code != 200:
        print(analyzed.text)
        return 1
    result = analyzed.json()["result"]
    for key in CATEGORIES:
        if key not in result:
            print("missing category", key)
            return 1
        items = result[key]
        if not isinstance(items, list):
            print("category is not a list", key)
            return 1
        for item in items:
            if not isinstance(item, dict) or not item.get("title") or not item.get("description"):
                print("finding missing title/description", key, item)
                return 1
    if result.get("processed_pages") is None:
        print("processed_pages missing")
        return 1
    if "findings across six categories" not in (result.get("summary") or ""):
        print("summary missing")
        return 1
    report = client.get(f"/api/v1/sow/requests/{handle}/report")
    print("report", report.status_code, report.headers.get("content-type"))
    if report.status_code != 200:
        print(report.text)
        return 1
    text = report.text
    for heading in (
        "Gray areas",
        "Risks",
        "Missing requirements",
        "Assumptions",
        "Dependencies",
        "Clarification questions",
        "Processed pages",
        "Summary",
    ):
        if heading not in text:
            print("report missing", heading)
            return 1
    print("SOW E2E via client proxy: OK", handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())

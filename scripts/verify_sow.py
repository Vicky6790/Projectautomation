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


def _sow_bytes() -> bytes:
    document = Document()
    document.add_paragraph(
        "The vendor shall deliver a customer portal in a reasonable time "
        "without defined acceptance criteria."
    )
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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
    for key in (
        "gray_areas",
        "risks",
        "missing_requirements",
        "assumptions",
        "dependencies",
        "clarification_questions",
    ):
        if key not in result:
            print("missing category", key)
            return 1
    report = client.get(f"/api/v1/sow/requests/{handle}/report")
    print("report", report.status_code, report.headers.get("content-type"))
    if report.status_code != 200:
        print(report.text)
        return 1
    print("SOW E2E via client proxy: OK", handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.errors import AppError
from app.models import ProcessingResponse
from app.reports import RETRO_SECTIONS, SOW_SECTIONS, WSR_SECTIONS, export_report
from tests.helpers import docx_bytes, pdf_text


def _job(module: str, status: str, result: dict | None) -> ProcessingResponse:
    now = datetime.now(UTC)
    return ProcessingResponse(
        id="11111111-1111-1111-1111-111111111111",
        request_handle="11111111-1111-1111-1111-111111111111",
        module=module,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        result=result,
        created_at=now,
        updated_at=now,
    )


def _complete_sow(client: TestClient) -> str:
    uploaded = client.post(
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
    handle = uploaded.json()["id"]
    client.post("/api/v1/sow/jobs", json={"file_id": handle})
    from app.storage import store

    store.set_status(
        handle,
        "succeeded",
        result={"risks": ["Scope may grow without change control"], "gray_areas": []},
    )
    return handle


def test_export_refuses_incomplete_job(client: TestClient) -> None:
    uploaded = client.post(
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
    handle = uploaded.json()["id"]
    client.post("/api/v1/sow/jobs", json={"file_id": handle})
    response = client.get(f"/api/v1/sow/jobs/{handle}/report")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "EXPORT_NOT_READY"
    assert "analysis must finish first" in error["message"].lower()


def test_export_includes_empty_sow_sections(client: TestClient) -> None:
    handle = _complete_sow(client)
    response = client.get(f"/api/v1/sow/requests/{handle}/report")
    assert response.status_code == 200
    text = response.text
    for _key, heading in SOW_SECTIONS:
        assert f"## {heading}" in text
    assert "Empty" in text
    assert "Scope may grow" in text
    disposition = response.headers["content-disposition"]
    assert "attachment;" in disposition
    assert handle in disposition
    assert response.headers["content-type"].startswith("text/markdown")


def test_sow_report_lists_every_category() -> None:
    filename, media, body = export_report(
        "sow",
        _job("sow", "succeeded", {"risks": ["Late vendor"], "gray_areas": []}),
    )
    text = body.decode()
    assert filename.endswith(".md")
    assert "11111111-1111-1111-1111-111111111111" in filename
    assert media.startswith("text/markdown")
    for _key, heading in SOW_SECTIONS:
        assert f"## {heading}" in text
    assert "- Late vendor" in text
    assert text.count("Empty") == 5


def test_wsr_report_matches_dashboard_sections() -> None:
    filename, media, body = export_report(
        "wsr",
        _job(
            "wsr",
            "succeeded",
            {
                "as_of_date": "2026-08-22",
                "generated_at": "2026-08-22T10:00:00Z",
                "planned_only": True,
                "exportable": True,
                "project_health": "on_track",
                "facts": {
                    "project_name": "Demo",
                    "project_owner": "Alex",
                    "as_of_date": "2026-08-22",
                    "generated_at": "2026-08-22T10:00:00Z",
                    "project_health": "on_track",
                    "executive_overview": "Demo is On track as of 2026-08-22.",
                    "overall_progress": 40,
                    "completed_work_items": 1,
                    "phase_count": 3,
                    "people_planned": 2,
                    "countdown_days": 20,
                    "planned_go_live_date": "2026-09-11",
                    "last_signed_off_milestone": {"name": "Kickoff", "date": "2026-08-10"},
                    "next_gate": {"name": "Go Live", "date": "2026-09-11"},
                    "timeline": None,
                    "phase_statuses": [],
                    "progress_to_date": [
                        {"name": "Kickoff", "date": "2026-08-10", "progress": 100}
                    ],
                    "upcoming_milestones": [{"name": "Go Live", "date": "2026-09-11"}],
                },
                "client_needs": [],
                "risks": [],
                "issues": [],
                "dependencies": [],
                "management_attention": [],
                "decisions_required": [],
                "next_7_day_priorities": [],
            },
        ),
    )
    assert filename.endswith(".pdf")
    assert media == "application/pdf"
    assert body.startswith(b"%PDF")
    text = " ".join(pdf_text(body).split())
    assert "WSR & Insights" in text
    assert "As of: 2026-08-22" in text
    assert "Generated: 2026-08-22T10:00:00Z" in text
    assert "On track" in text
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
    ):
        assert label in text
    for _key, heading in WSR_SECTIONS:
        assert heading in text
    for removed in (
        "What We Need From the Bank Team",
        "Management Attention",
        "Decisions Required",
    ):
        assert removed not in text
    assert "No items identified from the plan" in text
    assert "A timeline cannot be generated" in text
    assert "Unavailable" in text


def test_wsr_report_renders_timeline_without_zero_width_cells() -> None:
    filename, media, body = export_report(
        "wsr",
        _job(
            "wsr",
            "succeeded",
            {
                "as_of_date": "2026-08-22",
                "generated_at": "2026-08-22T10:00:00Z",
                "exportable": True,
                "project_health": "on_track",
                "facts": {
                    "project_name": "Demo",
                    "as_of_date": "2026-08-22",
                    "generated_at": "2026-08-22T10:00:00Z",
                    "project_health": "on_track",
                    "timeline": [
                        {
                            "name": "Kickoff",
                            "planned_start": "2026-08-01",
                            "planned_finish": "2026-08-10",
                            "state": "complete",
                            "progress": 100,
                        },
                        {
                            "name": "Build",
                            "planned_start": "2026-08-11",
                            "planned_finish": "2026-08-31",
                            "state": "in_progress",
                            "progress": 40,
                        },
                        {
                            "name": "Go Live",
                            "planned_start": "2026-09-01",
                            "planned_finish": "2026-09-11",
                            "state": "not_started",
                        },
                    ],
                    "phase_statuses": [
                        {
                            "name": "Kickoff",
                            "planned_start": "2026-08-01",
                            "planned_finish": "2026-08-10",
                            "state": "complete",
                            "progress": 100,
                        }
                    ],
                },
            },
        ),
    )
    assert filename.endswith(".pdf")
    assert media == "application/pdf"
    assert body.startswith(b"%PDF")
    text = " ".join(pdf_text(body).split())
    assert "Kickoff" in text
    assert "Build" in text
    assert "Go Live" in text
    assert "A timeline cannot be generated" not in text


def test_wsr_pending_insights_still_export() -> None:
    filename, media, body = export_report(
        "wsr",
        _job(
            "wsr",
            "succeeded",
            {
                "as_of_date": "2026-08-22",
                "generated_at": "2026-08-22T10:00:00Z",
                "exportable": False,
                "project_health": "on_track",
                "facts": {
                    "project_name": "Demo",
                    "as_of_date": "2026-08-22",
                    "generated_at": "2026-08-22T10:00:00Z",
                    "project_health": "on_track",
                },
                "risks": [
                    {
                        "id": "risk-1",
                        "section": "risk_or_focus_area",
                        "content": "Build may slip",
                        "review_status": "pending",
                        "evidence_references": [{"task_or_milestone_name": "Build"}],
                    }
                ],
            },
        ),
    )
    assert filename.endswith(".pdf")
    assert media == "application/pdf"
    text = pdf_text(body)
    assert "Build may slip" in text


def test_wsr_report_omits_removed_items() -> None:
    _filename, _media, body = export_report(
        "wsr",
        _job(
            "wsr",
            "succeeded",
            {
                "as_of_date": "2026-08-22",
                "generated_at": "2026-08-22T10:00:00Z",
                "exportable": True,
                "project_health": "on_track",
                "facts": {
                    "project_name": "Demo",
                    "as_of_date": "2026-08-22",
                    "generated_at": "2026-08-22T10:00:00Z",
                    "project_health": "on_track",
                },
                "risks": [
                    {
                        "id": "risk-1",
                        "section": "risk_or_focus_area",
                        "content": "Kept risk",
                        "review_status": "kept",
                        "evidence_references": [{"task_or_milestone_name": "Build"}],
                    },
                    {
                        "id": "risk-2",
                        "section": "risk_or_focus_area",
                        "content": "Removed risk",
                        "review_status": "removed",
                        "evidence_references": [{"task_or_milestone_name": "Kickoff"}],
                    },
                ],
                "issues": [
                    {
                        "id": "issue-1",
                        "section": "issue",
                        "content": "Removed issue",
                        "review_status": "removed",
                        "evidence_references": [{"task_or_milestone_name": "Build"}],
                    }
                ],
            },
        ),
    )
    text = pdf_text(body)
    assert "Kept risk" in text
    assert "Removed risk" not in text
    assert "Removed issue" not in text
    assert "No items identified from the plan" in text


def test_retro_report_includes_summary_and_seven_sections() -> None:
    _filename, _media, body = export_report(
        "retrospective",
        _job(
            "retrospective",
            "succeeded",
            {
                "summary": "Delivery slipped on Build",
                "planned_only": False,
                "what_went_poorly": ["Build"],
            },
        ),
    )
    text = body.decode()
    assert "Summary: Delivery slipped on Build" in text
    assert "Planned only: no" in text
    for _key, heading in RETRO_SECTIONS:
        assert f"## {heading}" in text
    assert "- Build" in text


def test_failed_job_cannot_export() -> None:
    try:
        export_report("sow", _job("sow", "failed", {"error": "nope"}))
    except AppError as exc:
        assert exc.code == "EXPORT_NOT_READY"
        assert "analysis must finish first" in exc.message.lower()
    else:
        raise AssertionError("expected EXPORT_NOT_READY")


def test_plan_has_no_document_report(client: TestClient) -> None:
    created = client.post("/api/v1/plan/jobs", json={})
    handle = created.json()["id"]
    from app.storage import store

    store.set_status(handle, "succeeded", result={"name": "preview"})
    response = client.get(f"/api/v1/plan/jobs/{handle}/report")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REPORT_NOT_SUPPORTED"

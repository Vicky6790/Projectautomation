from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import PlanTaskData, ProjectPlanData
from tests.helpers import mpp_stub_bytes, pdf_text


def _plan(*, status_date: str | None, planned_only: bool = True) -> ProjectPlanData:
    as_of = date.fromisoformat("2026-08-22")
    return ProjectPlanData(
        name="Demo",
        owner="Alex PM",
        status_date=status_date,
        has_actuals=not planned_only,
        planned_only=planned_only,
        tasks=[
            PlanTaskData(
                id=1,
                name="Kickoff",
                scheduled_start=(as_of - timedelta(days=10)).isoformat(),
                scheduled_finish=(as_of - timedelta(days=10)).isoformat(),
                baseline_finish=(as_of - timedelta(days=10)).isoformat(),
                percent_complete=100,
                actual_finish="2026-08-10",
            ),
            PlanTaskData(
                id=2,
                name="Build",
                scheduled_start=as_of.isoformat(),
                scheduled_finish=(as_of + timedelta(days=3)).isoformat(),
                baseline_finish=(as_of + timedelta(days=3)).isoformat(),
            ),
            PlanTaskData(
                id=3,
                name="Go Live",
                is_milestone=True,
                scheduled_finish=(as_of + timedelta(days=20)).isoformat(),
                baseline_finish=(as_of + timedelta(days=20)).isoformat(),
            ),
        ],
    )


def _upload(client: TestClient, monkeypatch, plan: ProjectPlanData) -> str:
    monkeypatch.setattr("app.routers.wsr.read_mpp_bytes", lambda _content, _name: plan)
    response = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", mpp_stub_bytes(), "application/vnd.ms-project")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["plan_available"] is True
    return response.json()["id"]


def _empty_ai(_data: dict) -> dict:
    return {
        "client_needs": [],
        "risks": [],
        "issues": [],
        "dependencies": [],
        "management_attention": [],
        "decisions_required": [],
        "next_7_day_priorities": [],
    }


def test_invalid_mpp_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", b"not-an-mpp", "application/vnd.ms-project")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_generate_uses_mpp_status_date(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", _empty_ai)
    response = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["as_of_date"] == "2026-08-22"
    assert result["generated_at"]
    assert result["facts"]["as_of_date"] == "2026-08-22"
    assert result["facts"]["project_health"] == "on_track"
    assert result["facts"]["planned_go_live_date"] == "2026-09-11"
    assert result["exportable"] is True
    assert result["milestones"] == ["Go Live"]
    status = client.get(f"/api/v1/wsr/requests/{handle}")
    assert status.json()["status"] == "succeeded"
    again = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert again.json()["result"]["generated_at"] == result["generated_at"]


def test_generate_falls_back_to_today_without_status_date(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date=None))
    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", _empty_ai)
    response = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert response.status_code == 200
    assert response.json()["result"]["as_of_date"] == datetime.now(UTC).date().isoformat()


def test_generate_retry_without_reupload(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    calls = {"n": 0}

    def flaky(_data: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return _empty_ai(_data)

    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", flaky)
    first = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert first.status_code == 502
    retry = client.post(f"/api/v1/wsr/jobs/{handle}/retry")
    assert retry.status_code == 200
    second = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert second.status_code == 200
    assert second.json()["result"]["project_health"] == "on_track"
    assert calls["n"] == 2


def test_report_available_after_generation(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", _empty_ai)
    client.post(f"/api/v1/wsr/requests/{handle}/generate")
    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("application/pdf")
    assert handle in report.headers["content-disposition"]
    assert ".pdf" in report.headers["content-disposition"]
    text = pdf_text(report.content)
    assert "WSR & Insights" in text
    assert "As of: 2026-08-22" in text
    assert "On track" in text
    for heading in (
        "Executive Overview",
        "Project Timeline",
        "Phase-Wise Status",
        "Progress to Date",
        "Upcoming Milestones",
        "Issues",
        "Risks & Focus Areas",
        "Next Seven-Day Priorities",
    ):
        assert heading in text
    for removed in (
        "What We Need From the Bank Team",
        "Dependencies",
        "Management Attention",
        "Decisions Required",
    ):
        assert removed not in text
    assert "No items identified from the plan" in text


def _pending_ai(_data: dict) -> dict:
    empty = _empty_ai(_data)
    empty["risks"] = [
        {
            "id": "risk-1",
            "section": "risk_or_focus_area",
            "content": "Build may slip before Go Live",
            "evidence_references": [
                {
                    "task_or_milestone_name": "Build",
                    "date": "2026-08-25",
                    "progress": 0,
                    "predecessor_names": ["Kickoff"],
                    "resource_assignments": ["Alex"],
                    "dependency_description": "Depends on Kickoff",
                }
            ],
            "review_status": "pending",
        }
    ]
    empty["issues"] = [
        {
            "id": "issue-1",
            "section": "issue",
            "content": "Kickoff evidence is incomplete",
            "evidence_references": [{"task_or_milestone_name": "Kickoff", "date": "2026-08-12"}],
            "review_status": "pending",
        }
    ]
    return empty


def _generate_pending(client: TestClient, monkeypatch) -> str:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", _pending_ai)
    response = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert response.status_code == 200, response.text
    assert response.json()["result"]["exportable"] is True
    return handle


def test_pending_insights_do_not_block_pdf(client: TestClient, monkeypatch) -> None:
    handle = _generate_pending(client, monkeypatch)
    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("application/pdf")
    text = pdf_text(report.content)
    assert "Build may slip before Go Live" in text
    jobs = client.get(f"/api/v1/wsr/jobs/{handle}/report")
    assert jobs.status_code == 200
    assert jobs.headers["content-type"].startswith("application/pdf")


def test_review_keep_edit_remove_and_download(client: TestClient, monkeypatch) -> None:
    handle = _generate_pending(client, monkeypatch)
    generated = client.get(f"/api/v1/wsr/requests/{handle}").json()["result"]
    generated_at = generated["generated_at"]
    as_of = generated["as_of_date"]

    missing = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/00000000-0000-0000-0000-000000000099",
        json={"decision": "kept"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ITEM_NOT_FOUND"

    blank = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/risk-1",
        json={"decision": "edited", "content": "   "},
    )
    assert blank.status_code == 400
    assert blank.json()["error"]["code"] == "INVALID_REVIEW"

    keep = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/issue-1",
        json={"decision": "kept"},
    )
    assert keep.status_code == 200
    assert keep.json()["result"]["exportable"] is False
    assert keep.json()["result"]["issues"][0]["review_status"] == "kept"

    edit = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/risk-1",
        json={"decision": "edited", "content": "Build is at risk against Go Live"},
    )
    assert edit.status_code == 200
    result = edit.json()["result"]
    assert result["exportable"] is True
    assert result["as_of_date"] == as_of
    assert result["generated_at"] == generated_at
    assert result["risks"][0]["content"] == "Build is at risk against Go Live"
    assert result["risks"][0]["review_status"] == "edited"

    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    assert report.status_code == 200
    text = pdf_text(report.content)
    assert "Build is at risk against Go Live" in text
    assert "Kickoff evidence is incomplete" in text

    removed = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/issue-1",
        json={"decision": "removed"},
    )
    assert removed.status_code == 200
    assert removed.json()["result"]["exportable"] is True
    assert removed.json()["result"]["issues"][0]["review_status"] == "removed"

    after_remove = client.get(f"/api/v1/wsr/requests/{handle}/report")
    assert after_remove.status_code == 200
    text = pdf_text(after_remove.content)
    assert "Kickoff evidence is incomplete" not in text
    assert "Build is at risk against Go Live" in text


def test_review_not_allowed_until_generation_succeeds(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))

    def boom(_data: dict) -> dict:
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", boom)
    failed = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert failed.status_code == 502
    review = client.patch(
        f"/api/v1/wsr/requests/{handle}/items/risk-1",
        json={"decision": "kept"},
    )
    assert review.status_code == 409
    assert review.json()["error"]["code"] == "REVIEW_NOT_ALLOWED"


def test_evidence_is_isolated_to_the_request(client: TestClient, monkeypatch) -> None:
    handle = _generate_pending(client, monkeypatch)
    evidence = client.get(f"/api/v1/wsr/requests/{handle}/items/risk-1/evidence")
    assert evidence.status_code == 200
    body = evidence.json()
    assert body["item_id"] == "risk-1"
    assert body["review_status"] == "pending"
    assert body["evidence_references"][0]["task_or_milestone_name"] == "Build"
    assert body["evidence_references"][0]["predecessor_names"] == ["Kickoff"]
    assert body["evidence_references"][0]["resource_assignments"] == ["Alex"]

    other = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", _empty_ai)
    generated = client.post(f"/api/v1/wsr/requests/{other}/generate")
    assert generated.status_code == 200
    isolated = client.get(f"/api/v1/wsr/requests/{other}/items/risk-1/evidence")
    assert isolated.status_code == 404
    assert isolated.json()["error"]["code"] == "ITEM_NOT_FOUND"
    patched = client.patch(
        f"/api/v1/wsr/requests/{other}/items/risk-1",
        json={"decision": "kept"},
    )
    assert patched.status_code == 404

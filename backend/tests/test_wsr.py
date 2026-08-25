from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import PlanTaskData, ProjectPlanData
from tests.helpers import mpp_stub_bytes


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
    assert "WSR & Insights" in report.text
    assert "As of: 2026-08-22" in report.text
    assert "On track" in report.text
    for heading in (
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
        assert heading in report.text
    assert "No items identified from the plan" in report.text

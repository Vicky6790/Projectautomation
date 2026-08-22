from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import PlanTaskData, ProjectPlanData, StatusReport


def _plan(*, status_date: str | None, planned_only: bool = True) -> ProjectPlanData:
    as_of = date.fromisoformat("2026-08-22")
    return ProjectPlanData(
        name="Demo",
        status_date=status_date,
        has_actuals=not planned_only,
        planned_only=planned_only,
        tasks=[
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish=(as_of - timedelta(days=10)).isoformat(),
                percent_complete=100,
                actual_finish="2026-08-10",
            ),
            PlanTaskData(
                id=2,
                name="Build",
                baseline_finish=(as_of + timedelta(days=3)).isoformat(),
            ),
            PlanTaskData(
                id=3,
                name="Go Live",
                is_milestone=True,
                baseline_finish=(as_of + timedelta(days=20)).isoformat(),
            ),
        ],
    )


def _upload(client: TestClient, monkeypatch, plan: ProjectPlanData) -> str:
    monkeypatch.setattr("app.routers.wsr.read_mpp_bytes", lambda _content, _name: plan)
    response = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", b"fake-mpp-bytes", "application/vnd.ms-project")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["plan_available"] is True
    return response.json()["id"]


def test_invalid_mpp_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("plan.mpp", b"not-an-mpp", "application/vnd.ms-project")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNREADABLE_MPP"


def test_generate_uses_mpp_status_date(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr(
        "app.orchestration.wsr.analyze_wsr",
        lambda data: StatusReport(
            project_health="on_track",
            as_of_date=data["as_of_date"],
            next_7_day_priorities=data["metrics"]["next_7_day_names"],
        ),
    )
    response = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    for key in (
        "project_health",
        "progress",
        "milestones",
        "risks",
        "issues",
        "dependencies",
        "management_attention",
        "decisions_required",
        "next_7_day_priorities",
    ):
        assert key in result
    assert result["as_of_date"] == "2026-08-22"
    assert "Build" in result["next_7_day_priorities"]
    status = client.get(f"/api/v1/wsr/requests/{handle}")
    assert status.json()["status"] == "succeeded"


def test_generate_falls_back_to_today_without_status_date(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date=None))
    monkeypatch.setattr(
        "app.orchestration.wsr.analyze_wsr",
        lambda data: StatusReport(as_of_date=data["as_of_date"], project_health="on_track"),
    )
    response = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert response.status_code == 200
    assert response.json()["result"]["as_of_date"] == datetime.now(UTC).date().isoformat()


def test_generate_retry_without_reupload(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    calls = {"n": 0}

    def flaky(_data: dict) -> StatusReport:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return StatusReport(project_health="at_risk", as_of_date="2026-08-22")

    monkeypatch.setattr("app.orchestration.wsr.analyze_wsr", flaky)
    first = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert first.status_code == 502
    retry = client.post(f"/api/v1/wsr/jobs/{handle}/retry")
    assert retry.status_code == 200
    second = client.post(f"/api/v1/wsr/requests/{handle}/generate")
    assert second.status_code == 200
    assert second.json()["result"]["project_health"] == "at_risk"
    assert calls["n"] == 2


def test_report_available_after_generation(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(status_date="2026-08-22"))
    monkeypatch.setattr(
        "app.orchestration.wsr.analyze_wsr",
        lambda _data: StatusReport(project_health="on_track", as_of_date="2026-08-22"),
    )
    client.post(f"/api/v1/wsr/requests/{handle}/generate")
    report = client.get(f"/api/v1/wsr/requests/{handle}/report")
    assert report.status_code == 200
    assert "Project health" in report.text
    assert "As of: 2026-08-22" in report.text
    for heading in (
        "Progress",
        "Milestones",
        "Risks",
        "Issues",
        "Dependencies",
        "Management attention",
        "Decisions required",
        "Next 7-day priorities",
    ):
        assert heading in report.text

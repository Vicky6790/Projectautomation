from fastapi.testclient import TestClient

from app.models import PlanTaskData, ProjectPlanData, RetrospectiveReport
from tests.helpers import mpp_stub_bytes


def _plan(*, planned_only: bool) -> ProjectPlanData:
    return ProjectPlanData(
        name="Demo",
        has_actuals=not planned_only,
        planned_only=planned_only,
        tasks=[
            PlanTaskData(
                id=1,
                name="Kickoff",
                baseline_finish="2026-08-01",
                actual_finish="2026-08-01",
                percent_complete=100,
            ),
            PlanTaskData(
                id=2,
                name="Build",
                baseline_finish="2026-08-10",
                actual_finish="2026-08-20",
                percent_complete=100,
            ),
            PlanTaskData(
                id=3,
                name="Go Live",
                is_milestone=True,
                baseline_finish="2026-09-01",
            ),
        ],
    )


def _upload(client: TestClient, monkeypatch, plan: ProjectPlanData) -> str:
    monkeypatch.setattr(
        "app.routers.retrospective.read_mpp_bytes",
        lambda _content, _name: plan,
    )
    response = client.post(
        "/api/v1/retrospective/uploads",
        files={"file": ("plan.mpp", mpp_stub_bytes(), "application/vnd.ms-project")},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_invalid_mpp_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/retrospective/uploads",
        files={"file": ("plan.mpp", b"not-an-mpp", "application/vnd.ms-project")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_generate_marks_planned_only(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(planned_only=True))
    response = client.post(f"/api/v1/retrospective/requests/{handle}/generate")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["planned_only"] is True
    for key in (
        "schedule_variance",
        "milestone_delivery",
        "task_completion",
        "what_went_well",
        "what_went_poorly",
        "lessons_learned",
        "recommendations",
    ):
        assert key in result


def test_generate_uses_actuals_when_present(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(planned_only=False))
    monkeypatch.setattr(
        "app.orchestration.retrospective.analyze_retrospective",
        lambda data: RetrospectiveReport(
            planned_only=data["planned_only"],
            what_went_poorly=data["metrics"]["slipped_names"],
            what_went_well=data["metrics"]["on_time_names"],
        ),
    )
    response = client.post(f"/api/v1/retrospective/requests/{handle}/generate")
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["planned_only"] is False
    assert "Build" in result["what_went_poorly"]
    assert "Kickoff" in result["what_went_well"]


def test_generate_retry_without_reupload(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(planned_only=False))
    calls = {"n": 0}

    def flaky(_data: dict) -> RetrospectiveReport:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return RetrospectiveReport(summary="Retry worked", planned_only=False)

    monkeypatch.setattr("app.orchestration.retrospective.analyze_retrospective", flaky)
    first = client.post(f"/api/v1/retrospective/requests/{handle}/generate")
    assert first.status_code == 502
    retry = client.post(f"/api/v1/retrospective/jobs/{handle}/retry")
    assert retry.status_code == 200
    second = client.post(f"/api/v1/retrospective/requests/{handle}/generate")
    assert second.status_code == 200
    assert second.json()["result"]["summary"] == "Retry worked"
    assert calls["n"] == 2


def test_report_available_after_generation(client: TestClient, monkeypatch) -> None:
    handle = _upload(client, monkeypatch, _plan(planned_only=True))
    client.post(f"/api/v1/retrospective/requests/{handle}/generate")
    report = client.get(f"/api/v1/retrospective/requests/{handle}/report")
    assert report.status_code == 200
    assert "Planned only: yes" in report.text
    for heading in (
        "Schedule variance",
        "Milestone delivery",
        "Task completion",
        "What went well",
        "What went poorly",
        "Lessons learned",
        "Recommendations",
    ):
        assert heading in report.text

from fastapi.testclient import TestClient

from app.models import AnalysisReport
from tests.helpers import docx_bytes


def _upload_sow(client: TestClient) -> str:
    response = client.post(
        "/api/v1/sow/uploads",
        files={
            "file": (
                "sow.docx",
                docx_bytes("The vendor shall deliver a portal in a reasonable time."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_analyze_returns_six_categories(client: TestClient, monkeypatch) -> None:
    handle = _upload_sow(client)
    monkeypatch.setattr(
        "app.orchestration.sow.analyze_sow",
        lambda _text: AnalysisReport(
            gray_areas=[
                {
                    "category": "gray_areas",
                    "title": "Reasonable is undefined",
                    "description": "Reasonable is undefined",
                    "recommendation": "Define measurable acceptance criteria.",
                }
            ],
            risks=[
                {
                    "category": "risks",
                    "title": "Schedule may slip",
                    "description": "Schedule may slip",
                    "recommendation": "Add a delivery date and milestone reviews.",
                }
            ],
        ),
    )
    response = client.post(f"/api/v1/sow/requests/{handle}/analyze")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    for key in (
        "gray_areas",
        "risks",
        "missing_requirements",
        "assumptions",
        "dependencies",
        "clarification_questions",
    ):
        assert key in result
    assert result["gray_areas"][0]["description"] == "Reasonable is undefined"
    assert result["gray_areas"][0]["recommendation"]
    assert result["assumptions"] == []
    assert result["processed_pages"] == 1
    assert "six categories" in result["summary"]
    status = client.get(f"/api/v1/sow/requests/{handle}")
    assert status.json()["status"] == "succeeded"


def test_analyze_keeps_model_summary(client: TestClient, monkeypatch) -> None:
    handle = _upload_sow(client)
    monkeypatch.setattr(
        "app.orchestration.sow.analyze_sow",
        lambda _text: AnalysisReport(
            summary="Acceptance criteria are missing from the signed SOW.",
            risks=[
                {
                    "category": "risks",
                    "priority": "high",
                    "title": "Schedule risk",
                    "description": "No delivery date is stated.",
                    "recommendation": "Add a dated milestone.",
                }
            ],
        ),
    )
    response = client.post(f"/api/v1/sow/requests/{handle}/analyze")
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["summary"] == "Acceptance criteria are missing from the signed SOW."
    assert result["risks"][0]["priority"] == "high"


def test_analyze_retry_without_reupload(client: TestClient, monkeypatch) -> None:
    handle = _upload_sow(client)
    calls = {"n": 0}

    def flaky(_text: str) -> AnalysisReport:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider down")
        return AnalysisReport(risks=[{"title": "Retry worked", "description": "Retry worked"}])

    monkeypatch.setattr("app.orchestration.sow.analyze_sow", flaky)
    first = client.post(f"/api/v1/sow/requests/{handle}/analyze")
    assert first.status_code == 502
    retry = client.post("/api/v1/sow/jobs/" + handle + "/retry")
    assert retry.status_code == 200
    second = client.post(f"/api/v1/sow/requests/{handle}/analyze")
    assert second.status_code == 200
    assert second.json()["result"]["risks"][0]["description"] == "Retry worked"
    assert calls["n"] == 2


def test_report_available_after_analysis(client: TestClient, monkeypatch) -> None:
    handle = _upload_sow(client)
    monkeypatch.setattr("app.orchestration.sow.analyze_sow", lambda _text: AnalysisReport())
    client.post(f"/api/v1/sow/requests/{handle}/analyze")
    report = client.get(f"/api/v1/sow/requests/{handle}/report")
    assert report.status_code == 200
    assert "Gray areas" in report.text

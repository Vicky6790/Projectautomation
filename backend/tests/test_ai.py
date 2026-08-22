import json

import pytest

from app.ai import client as ai_client
from app.ai import engine
from app.errors import AppError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | str) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self) -> dict:
        if isinstance(self._payload, dict):
            return self._payload
        raise ValueError("not json")


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


class _SeqClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, _url, json=None, headers=None):
        self.calls += 1
        return self.responses.pop(0)


def _sow_payload() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "gray_areas": ["Term 'reasonable' is undefined"],
                            "risks": [],
                            "missing_requirements": ["No acceptance criteria"],
                            "assumptions": [],
                            "dependencies": [],
                            "clarification_questions": ["What is the go-live date?"],
                        }
                    )
                }
            }
        ]
    }


def test_analyze_sow_stub_skips_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", True)
    monkeypatch.setattr(settings, "openai_api_key", "")
    result = engine.analyze_sow("The vendor shall deliver a portal.")
    assert result.gray_areas
    assert result.risks == []


def test_analyze_sow_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("A statement of work.")
    assert exc.value.code == "AI_NOT_CONFIGURED"
    assert exc.value.retryable is False


def test_analyze_sow_parses_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    fake = _FakeClient(_FakeResponse(200, _sow_payload()))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    result = engine.analyze_sow("The vendor shall deliver a portal in a reasonable time.")
    assert result.gray_areas == ["Term 'reasonable' is undefined"]
    assert result.risks == []
    assert result.missing_requirements == ["No acceptance criteria"]
    assert result.clarification_questions


def test_analyze_sow_retries_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    payload = {"choices": [{"message": {"content": "not-json"}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("SOW text")
    assert exc.value.code == "AI_PARSE_FAILED"
    assert exc.value.retryable is True


def test_analyze_sow_schema_mismatch_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    payload = {"choices": [{"message": {"content": json.dumps({"gray_areas": 12})}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("SOW text")
    assert exc.value.code == "AI_PARSE_FAILED"
    assert exc.value.retryable is True


def test_analyze_wsr_uses_plan_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    body = {
        "project_health": "at_risk",
        "progress": ["12 of 20 tasks complete"],
        "milestones": [],
        "risks": ["Vendor delay"],
        "issues": [],
        "dependencies": [],
        "management_attention": [],
        "decisions_required": [],
        "next_7_day_priorities": ["Close design review"],
    }
    payload = {"choices": [{"message": {"content": json.dumps(body)}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    result = engine.analyze_wsr(
        {
            "as_of_date": "2026-08-22",
            "planned_only": True,
            "metrics": {"overdue_count": 2},
        }
    )
    assert result.project_health == "at_risk"
    assert result.risks == ["Vendor delay"]
    assert result.milestones == []
    assert result.as_of_date == "2026-08-22"
    assert result.planned_only is True


def test_wsr_outbound_omits_task_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    body = {
        "project_health": "on_track",
        "progress": [],
        "milestones": [],
        "risks": [],
        "issues": [],
        "dependencies": [],
        "management_attention": [],
        "decisions_required": [],
        "next_7_day_priorities": [],
    }
    payload = {"choices": [{"message": {"content": json.dumps(body)}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    engine.analyze_wsr(
        {
            "as_of_date": "2026-08-22",
            "planned_only": True,
            "tasks": [{"name": "Confidential Vendor Task", "baseline_finish": "2026-09-01"}],
            "metrics": {"overdue_count": 0, "progress_notes": ["ok"]},
        }
    )
    user_content = fake.calls[0]["json"]["messages"][1]["content"]
    assert "Confidential Vendor Task" not in user_content
    assert "overdue_count" in user_content
    assert "task_count" in user_content


def test_analyze_retrospective_sets_planned_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    body = {
        "summary": "No actuals yet",
        "schedule_variance": [],
        "milestone_delivery": [],
        "task_completion": [],
        "what_went_well": [],
        "what_went_poorly": [],
        "lessons_learned": None,
        "recommendations": [],
        "planned_only": False,
    }
    payload = {"choices": [{"message": {"content": json.dumps(body)}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    result = engine.analyze_retrospective({"planned_only": True, "metrics": {}})
    assert result.planned_only is True
    assert result.lessons_learned == []


def test_retry_after_transient_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_client.time, "sleep", lambda _seconds: None)
    seq = _SeqClient([_FakeResponse(429, {}), _FakeResponse(200, _sow_payload())])
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: seq)
    result = engine.analyze_sow("SOW text for retry")
    assert result.gray_areas
    assert seq.calls == 2


def test_provider_auth_error_is_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_stub", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    fake = _FakeClient(_FakeResponse(401, {"error": "unauthorized"}))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("SOW text")
    assert exc.value.code == "AI_PROVIDER_REJECTED"
    assert exc.value.retryable is False
    assert len(fake.calls) == 1


def test_azure_uses_api_key_header_and_existing_completions_path() -> None:
    url = (
        "https://demo.openai.azure.com/openai/deployments/gpt/chat/completions"
        "?api-version=2024-02-15-preview"
    )
    assert ai_client.completions_url(url) == url
    headers = ai_client.provider_headers(url, "azure-key")
    assert headers["api-key"] == "azure-key"
    assert "Authorization" not in headers

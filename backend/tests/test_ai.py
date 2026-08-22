import json

import pytest

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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, _url, json=None, headers=None):
        return self.response


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


def test_analyze_sow_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("A statement of work.")
    assert exc.value.code == "AI_NOT_CONFIGURED"
    assert exc.value.retryable is False


def test_analyze_sow_parses_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

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

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    payload = {"choices": [{"message": {"content": "not-json"}}]}
    fake = _FakeClient(_FakeResponse(200, payload))
    monkeypatch.setattr("app.ai.client.httpx.Client", lambda **_kwargs: fake)
    with pytest.raises(AppError) as exc:
        engine.analyze_sow("SOW text")
    assert exc.value.code == "AI_PARSE_FAILED"
    assert exc.value.retryable is True


def test_analyze_wsr_uses_plan_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

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
    result = engine.analyze_wsr({"as_of": "2026-08-22", "late_tasks": 2})
    assert result.project_health == "at_risk"
    assert result.risks == ["Vendor delay"]
    assert result.milestones == []

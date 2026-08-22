from __future__ import annotations

import json
import time

import httpx

from app.config import settings
from app.errors import AppError

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAiClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        if not settings.openai_api_key:
            raise AppError(
                503,
                "AI_NOT_CONFIGURED",
                "OPENAI_API_KEY is not configured",
                retryable=False,
            )
        url = completions_url(settings.openai_base_url)
        payload = {
            "model": settings.openai_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = provider_headers(url, settings.openai_api_key)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=settings.openai_timeout_seconds) as client:
                    response = client.post(url, json=payload, headers=headers)
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = AppError(
                        503,
                        "AI_PROVIDER_UNAVAILABLE",
                        "The AI provider is temporarily unavailable",
                        retryable=True,
                    )
                    time.sleep(0.2 * (attempt + 1))
                    continue
                if 400 <= response.status_code < 500:
                    raise AppError(
                        502,
                        "AI_PROVIDER_REJECTED",
                        "The AI provider rejected the request",
                        retryable=False,
                    )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return _parse_json_object(content)
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider failures are caller errors
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        raise AppError(
            503,
            "AI_PROVIDER_UNAVAILABLE",
            "The AI provider request failed",
            retryable=True,
        ) from last_error


def completions_url(base_url: str) -> str:
    url = base_url.strip()
    if "chat/completions" in url:
        return url
    return f"{url.rstrip('/')}/chat/completions"


def provider_headers(url: str, api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if "openai.azure.com" in url.lower() or "azure" in url.lower():
        headers["api-key"] = api_key
        return headers
    headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            502,
            "AI_PARSE_FAILED",
            "The AI response was not valid JSON",
            retryable=True,
        ) from exc
    if not isinstance(parsed, dict):
        raise AppError(
            502,
            "AI_PARSE_FAILED",
            "The AI response was not a JSON object",
            retryable=True,
        )
    return parsed

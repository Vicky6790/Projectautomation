"""Shared browser-session helper for Compose verification scripts."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE = os.environ.get("APP_BASE_URL", "http://localhost:8080")


def ensure_session(client: httpx.Client, health: dict[str, Any] | None = None) -> None:
    payload = health
    if payload is None:
        response = client.get("/health")
        response.raise_for_status()
        payload = response.json()
    if not payload.get("auth_required"):
        return
    username = os.environ.get("AUTH_BOOTSTRAP_USER", "admin")
    password = os.environ.get("AUTH_BOOTSTRAP_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "AUTH_MODE=required: set AUTH_BOOTSTRAP_PASSWORD before running this script"
        )
    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    if login.status_code != 200:
        raise RuntimeError(f"sign-in failed: {login.status_code} {login.text}")

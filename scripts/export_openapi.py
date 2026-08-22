"""Export the live FastAPI OpenAPI document to docs/openapi.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app

DEST = ROOT / "docs" / "openapi.json"

FROZEN_PATHS = (
    "/health",
    "/ready",
    "/api/v1/sow/uploads",
    "/api/v1/sow/requests/{handle}/analyze",
    "/api/v1/sow/requests/{handle}",
    "/api/v1/sow/requests/{handle}/report",
    "/api/v1/plan/library",
    "/api/v1/plan/preview",
    "/api/v1/plan/requests/{handle}",
    "/api/v1/plan/requests/{handle}/approve",
    "/api/v1/plan/requests/{handle}/mpp",
    "/api/v1/wsr/uploads",
    "/api/v1/wsr/requests/{handle}/generate",
    "/api/v1/wsr/requests/{handle}",
    "/api/v1/wsr/requests/{handle}/report",
    "/api/v1/retrospective/uploads",
    "/api/v1/retrospective/requests/{handle}/generate",
    "/api/v1/retrospective/requests/{handle}",
    "/api/v1/retrospective/requests/{handle}/report",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
)


def schema() -> dict:
    return create_app().openapi()


def write() -> Path:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DEST


if __name__ == "__main__":
    path = write()
    print("wrote", path)

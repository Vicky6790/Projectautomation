"""Export the live FastAPI OpenAPI document to docs/openapi.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.openapi_contract import FROZEN_PATHS  # noqa: E402

DEST = ROOT / "docs" / "openapi.json"


def schema() -> dict:
    return create_app().openapi()


def write() -> Path:
    payload = schema()
    missing = [path for path in FROZEN_PATHS if path not in payload["paths"]]
    if missing:
        raise SystemExit(f"frozen paths missing from live schema: {missing}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DEST


if __name__ == "__main__":
    path = write()
    print("wrote", path)

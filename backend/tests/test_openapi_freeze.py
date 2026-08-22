import json
from pathlib import Path

from app.main import create_app
from app.openapi_contract import FROZEN_PATHS

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "docs" / "openapi.json"


def test_frozen_openapi_matches_live_schema() -> None:
    live = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    assert FROZEN.exists(), "docs/openapi.json is missing; run python scripts/export_openapi.py"
    assert FROZEN.read_text(encoding="utf-8") == live


def test_frozen_contract_paths_and_status_model() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    for path in FROZEN_PATHS:
        assert path in paths, path
    processing = schema["components"]["schemas"]["ProcessingResponse"]
    status = processing["properties"]["status"]
    names = set(status.get("enum") or status.get("anyOf", [{}])[0].get("enum") or [])
    if not names and "anyOf" in status:
        for option in status["anyOf"]:
            names.update(option.get("enum") or [])
    assert {"queued", "running", "succeeded", "failed"} <= names
    error = schema["components"]["schemas"]["ApiError"]
    for field in ("code", "message", "retryable"):
        assert field in error["properties"]

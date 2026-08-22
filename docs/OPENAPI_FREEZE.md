# OpenAPI freeze (WO-36)

Frozen document: `docs/openapi.json` (export with `python scripts/export_openapi.py`).

CI/local check: `pytest backend/tests/test_openapi_freeze.py`.

## Blueprint → live mapping

| API Server blueprint | Frozen implementation |
|---------------------|----------------------|
| `/api/sow/...` | `/api/v1/sow/...` |
| `/api/plans/...` | `/api/v1/plan/...` |
| `/api/wsr/...` | `/api/v1/wsr/...` |
| `/api/retrospectives/...` | `/api/v1/retrospective/...` |
| `ProcessingResponse.state` processing / complete / failed | `ProcessingResponse.status` queued / running / succeeded / failed |
| `ApiError.retryable` | `error.retryable` |
| Plan preview then MPP | `POST /api/v1/plan/preview` then `POST .../approve` then `GET .../mpp` |

## Required frozen paths

Health `/health`, `/ready`, module upload / process / status / download routes, and auth `login` / `logout` / `me` listed in `backend/tests/test_openapi_freeze.py`.

Do not change those paths or the status enum without updating this freeze and WO-36.

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

Canonical list: `backend/app/openapi_contract.py` (imported by the freeze test and `scripts/export_openapi.py`).

Includes health `/health` `/ready`, generic `POST /api/v1/files`, module request-handle upload/process/status/download, client job start/status/retry aliases, plan preview retry, and auth `login` / `logout` / `me` / `users` / `users/{operator_id}/disable`.

After WO-35, auth routes are part of this freeze (WO-36 originally deferred them). No extra WO.

Do not change those paths or the status enum without updating this freeze and WO-36.

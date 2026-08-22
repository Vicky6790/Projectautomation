# Foundation validation (WO-33)

Checked 2026-08-22 against the API Server and Client App container blueprints.

## API Server — aligned

- FastAPI/Uvicorn in a Docker image with JRE 17 for MPXJ/JPype
- Compose starts API + Client; only the client port is published
- Persistent request storage on `DATA_DIR` (`/data`), TTL `REQUEST_TTL_HOURS` (24)
- Health (`/health`) and readiness (`/ready`) for Compose
- `ApiError` shape: `code`, `message`, `retryable`
- Local auth off (`AUTH_MODE=disabled`); on-prem multi-user is WO-31 / WO-35
- Plan generation does not accept a reference MPP
- OpenAI is optional locally (`AI_STUB=true`); `OPENAI_BASE_URL` is the residency override

## Client App — aligned

- React SPA with four module views and no business processing
- nginx serves the bundle and proxies `/api` (and health/ready) to the API over the Compose network
- Upload progress and cancel on file modules
- Processing and retriable errors are shown; downloads use completed request handles

## Accepted deviations (no extra WO)

| Blueprint | Implementation | Call |
|-----------|----------------|------|
| Routes under `/api/...` | Versioned `/api/v1/...` | Keep `/api/v1`; freeze in OpenAPI |
| `ProcessingResponse.state` = processing/complete/failed | `status` = queued/running/succeeded/failed | Same lifecycle, different names |
| Poll while `processing` | Module generate/analyze/preview calls are synchronous HTTP | nginx `proxy_read_timeout` 300s; acceptable for MVP |

## Follow-up already on the board

- WO-31 / WO-35 — on-prem authentication (`in_review`)
- WO-34 — on-prem Compose verification (`docs/ONPREM_COMPOSE.md`)
- WO-36 — freeze OpenAPI (`in_review`)

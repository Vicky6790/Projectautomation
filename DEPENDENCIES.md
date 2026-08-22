# Work-order dependency map

Factory MCP could not be updated from this session. Apply these status/dependency changes in Factory when the connection is healthy.

## This increment (implemented in repo)

| WO | Intent | Status to set | Notes |
|----|--------|---------------|--------|
| WO-15 | Cross-module API contracts | `completed` (already) | Encoded as FastAPI models + routes |
| WO-1 | FastAPI skeleton + API Dockerfile | `in_review` | Health, CORS, errors, job/file routers, Python+JRE 17 image |
| WO-6 | React scaffold + client Dockerfile | `in_review` | Vite + React, nginx image, `/api` proxy |
| WO-26 | Compose deployment | starter only | `docker-compose.yml` added; on-prem/Windows runbook still open |

## Explicitly not implemented (blockers remain)

| WO | Depends on | Why blocked |
|----|----------|-------------|
| WO-2 | WO-1 | Document ingestion (PDF/DOCX extract) not built |
| WO-3 | WO-1 | AI analysis / OpenAI adapter not built |
| WO-4 | WO-1 | MPP/MPXJ processing not built (needs Java 17) |
| WO-5 | WO-1 | Report export/download payloads not generated |
| WO-20 | WO-1 | Template library required before Plan Generator API |
| WO-7 | WO-2, WO-3, WO-5 | SOW Analyzer API |
| WO-8 | WO-4, WO-20 | Plan Generator API |
| WO-9 | WO-2, WO-3, WO-4, WO-5 | WSR API |
| WO-10 | WO-2, WO-3, WO-4, WO-5 | Retrospective API |
| WO-11–14 | WO-6 + matching API | UI modules |
| WO-16–19 | matching API + UI | E2E |

## Integration gap closed in code

Stub routers exist for SOW / WSR / Retrospective / Plan **start / status / retry** plus upload/download, using the shared `ProcessingResponse` / `ApiError` shapes. They persist jobs on disk but do **not** call ingestion, AI, MPXJ, or exporters.

## Recommended new work orders (if missing in Factory)

1. **OpenAPI contract freeze** — generate `openapi.json` from this app and diff against the API Server blueprint.
2. **Auth adapter** — enable `AUTH_MODE=required` for on-prem multi-user (out of local MVP).

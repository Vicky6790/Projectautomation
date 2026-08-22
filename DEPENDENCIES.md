# Work-order dependency map

Factory statuses were updated in this increment where the MCP allowed it.

## This increment (implemented in repo)

| WO | Intent | Status to set | Notes |
|----|--------|---------------|--------|
| WO-15 | Cross-module API contracts | `completed` (already) | Encoded as FastAPI models + routes |
| WO-1 | FastAPI skeleton + API Dockerfile | `in_review` | Health, CORS, errors, job/file routers, Python+JRE 17 image |
| WO-6 | React scaffold + client Dockerfile | `in_review` | Vite + React, nginx image, `/api` proxy |
| WO-24 | Upload format and size policies | `completed` | SOW PDF/DOCX 25 MB; MPP 50 MB |
| WO-25 | Connect source repository | `completed` | GitHub `Vicky6790/Projectautomation` |
| WO-2 | Document ingestion | `in_review` | Type/size validation + SOW text extraction |
| WO-30 | Request retention policy | `completed` | 24h idle TTL on DATA_DIR; survives host restart |
| WO-32 | Request-handle lifecycle | `in_review` | Idempotent handle, retry, isolation, TTL cleanup |
| WO-28 | OpenAI residency policy | `completed` | Public OpenAI by default; Azure/on-prem via OPENAI_BASE_URL |
| WO-5 | Report export | `in_review` | Markdown export of SOW/WSR/retro; empty sections kept |
| WO-29 | SOW classification criteria | `completed` | Six finding categories with empty-list rule |
| WO-27 | WSR/retro classification criteria | `completed` | Health thresholds and evidence rules |
| WO-3 | AI analysis service | `in_review` | OpenAI client + engine emitting report schemas |
| WO-26 | Compose deployment | starter only | `docker-compose.yml` added; on-prem/Windows runbook still open |

## Explicitly not implemented (blockers remain)

| WO | Depends on | Why blocked |
|----|----------|-------------|
| WO-4 | WO-1 | MPP/MPXJ processing not built (needs Java 17) |
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

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
| WO-4 | MPP processing | `in_review` | MPXJ reader/writer; generated file is MSPDI XML |
| WO-7 | SOW Analyzer API | `in_review` | Upload, analyze, retry, report; six categories always present |
| WO-11 | SOW Analyzer UI | `in_review` | Upload, category findings, retry, report download |
| WO-26 | Compose deployment | `in_review` | Local Compose + on-prem overlay; API not published on host |
| WO-16 | SOW E2E via Compose | `in_review` | Proxy path verified: upload → analyze → report |
| WO-23 | Template library content | `completed` | Digital delivery phases, sets, CMS prereq, FS rules |
| WO-20 | Template library expansion | `in_review` | Deterministic WBS expand; GET /api/v1/plan/library |
| WO-22 | Phase sequence validation | `in_review` | Empty config, set counts, sequence conflicts |
| WO-8 | Plan Generator API | `in_review` | Preview, retry, approve, MSPDI download |
| WO-21 | Configurable phase order in UI | `in_review` | Add/remove/reorder phases; empty and sequence errors |
| WO-12 | Plan Generator view | `in_review` | Deliverables, set counts, WBS review, approve, MPP download |
| WO-17 | Plan Generator E2E via Compose | `in_review` | Proxy path: library → preview → approve → MSPDI download |
| WO-9 | WSR Generator API | `in_review` | MPP upload, as-of date, nine-section StatusReport, retry, markdown export |
| WO-13 | WSR Generator view | `in_review` | MPP upload, nine-section dashboard, health, retry, report download |
| WO-18 | WSR E2E via Compose | `in_review` | Proxy path: MPP upload → generate → nine-section report |
| WO-10 | Retrospective API | `in_review` | MPP upload, planned-vs-actual, seven-section report, planned-only flag, retry |
| WO-14 | Retrospective view | `in_review` | MPP upload, seven-section retrospective, planned-only banner, retry, report download |
| WO-19 | Retrospective E2E via Compose | `in_review` | Proxy path: MPP upload → generate → seven-section report |
| WO-33 | Foundation validation vs blueprints | `in_review` | Health/ready, SPA shells, internal API; notes in docs/FOUNDATION_VALIDATION.md |
| WO-36 | OpenAPI freeze | `in_review` | docs/openapi.json plus pytest drift check; mapping in docs/OPENAPI_FREEZE.md |
| WO-31 | On-premise access-control requirements | `in_review` | Feature On-Premise Access Control; mapping in docs/ONPREM_AUTH.md |
| WO-35 | Implement on-prem authentication | `in_review` | Sessions, isolation, audit, on-prem AUTH_MODE=required |
| WO-34 | On-prem Compose verification | `in_review` | Overlay AUTH_MODE=required, persistent data dir, `scripts/verify_onprem.py` |

## Remaining environment check

Physical host sign-off of port 80 and the production `ONPREM_DATA_DIR` path is the same WO-34 runbook on the target server. No extra work order: `docs/ONPREM_COMPOSE.md`.

## Integration gap closed in code

SOW, Plan Generator, WSR, and Retrospective APIs persist jobs on disk and call ingestion, AI, and MPXJ. WSR and Retrospective dashboards are wired to those APIs.

## Recommended new work orders (if missing in Factory)

None. WO-34 runbook covers host sign-off of port 80 and `ONPREM_DATA_DIR`.

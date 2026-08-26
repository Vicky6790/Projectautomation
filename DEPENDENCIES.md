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
| WO-2 | Document ingestion | `in_review` | WO-24 type/size; PDF/DOCX text (tables); MPP magic-byte type check |
| WO-30 | Request retention policy | `completed` | 24h idle TTL on DATA_DIR; survives host restart |
| WO-32 | Request-handle lifecycle | `in_review` | Idempotent handle, retry, isolation, TTL cleanup |
| WO-28 | OpenAI residency policy | `completed` | Public OpenAI by default; Azure/on-prem via OPENAI_BASE_URL |
| WO-5 | Report export | `in_review` | WSR PDF from dashboard HTML; SOW/retro stay Markdown; Team Capacity from actual vs planned work |
| WO-29 | SOW classification criteria | `completed` | Six finding categories with empty-list rule |
| WO-27 | WSR/retro classification criteria | `completed` | Health thresholds and evidence rules |
| WO-3 | AI analysis service | `in_review` | WO-28 summary-only outbound; Azure api-key; schema parse retryable |
| WO-4 | MPP processing | `blocked` | Native write waits on WO-38; WSR reader is WO-40 |
| WO-40 | WSR MPP reader projection | `in_review` | Identity, dates, Gate alias, assignments; absent values stay unavailable |
| WO-7 | SOW Analyzer API | `in_review` | Structured findings (priority, title, description, recommendation); six categories always present |
| WO-11 | SOW Analyzer UI | `in_review` | Upload, start analysis, summary counts, finding cards, report download |
| WO-26 | Compose deployment | `in_review` | Local Compose + on-prem overlay; API not published on host |
| WO-16 | SOW E2E via Compose | `in_review` | Waits on WO-18; proxy path: upload → analyze → report |
| WO-23 | Template library content | `completed` | Digital delivery phases, sets, CMS prereq, FS rules |
| WO-20 | Template library expansion | `in_review` | Deterministic WBS expand; GET /api/v1/plan/library |
| WO-22 | Phase sequence validation | `in_review` | Empty config, set counts, sequence conflicts |
| WO-8 | Plan Generator API | `in_review` | Preview, retry, approve, MSPDI download |
| WO-21 | Configurable phase order in UI | `in_review` | Add/remove/reorder phases; empty and sequence errors |
| WO-12 | Plan Generator view | `in_review` | Deliverables, set counts, WBS review, approve, MPP download |
| WO-17 | Plan Generator E2E via Compose | `blocked` | Waits on WO-18 and native MPP (WO-4/WO-8/WO-12) |
| WO-9 | WSR Generator API | `in_review` | Direct MPP values plus plan-based narrative; exportable on generate |
| WO-41 | WSR insight review API | `cancelled` | Out of V1; unused review/evidence routes remain in OpenAPI freeze only |
| WO-39 | WSR insight review panel | `cancelled` | Out of V1; dashboard has no Keep/Edit/Remove or View Source |
| WO-13 | WSR Generator view | `in_review` | Approved dashboard, generation stages, PDF download after generate |
| WO-18 | WSR E2E via Compose | `in_review` | Proxy path: upload → generate → dashboard → PDF at localhost:8080 |
| WO-10 | Retrospective API | `in_review` | MPP upload, planned-vs-actual, seven-section report, planned-only flag, retry |
| WO-14 | Retrospective view | `in_review` | MPP upload, seven-section retrospective, planned-only banner, retry, report download |
| WO-19 | Retrospective E2E via Compose | `in_review` | Waits on WO-18; proxy path: MPP upload → generate → seven-section report |
| WO-33 | Foundation validation vs blueprints | `in_review` | Health/ready, SPA shells, internal API; notes in docs/FOUNDATION_VALIDATION.md |
| WO-36 | OpenAPI freeze | `in_review` | docs/openapi.json plus pytest drift check; mapping in docs/OPENAPI_FREEZE.md |
| WO-31 | On-premise access-control requirements | `in_review` | Feature On-Premise Access Control; mapping in docs/ONPREM_AUTH.md |
| WO-35 | Implement on-prem authentication | `in_review` | Sessions, isolation, audit, on-prem AUTH_MODE=required |
| WO-34 | On-prem Compose verification | `in_review` | Overlay AUTH_MODE=required, persistent data dir, `scripts/verify_onprem.py` |

## First deploy: WSR only

Factory clarification 2026-08-25: ship **WSR & Insights** end-to-end before SOW, Plan Generator, or Retrospective. Shared foundations stay in play; those other modules stay in the repo but are not this increment.

| Order | WO | Role |
|-------|----|------|
| 1 | WO-40 | MPP reader projection for WSR facts |
| 2 | WO-9 | WSR generation API and plan-based narrative |
| 3 | WO-5 | Approved WSR PDF export |
| 4 | WO-13 | Dashboard |
| 5 | WO-18 | Compose E2E (WSR path only) |
| Shared | WO-1, WO-2, WO-3, WO-6, WO-26, WO-32 | Already implemented enough to run WO-40 |

WO-38 native MPP write does **not** block this slice. WO-39 and WO-41 are cancelled for V1. SOW/Plan/Retro E2E (WO-16, WO-17, WO-19) are blocked by WO-18 until WSR is accepted.

## Remaining environment check

Physical host sign-off of port 80 and the production `ONPREM_DATA_DIR` path is the same WO-34 runbook on the target server. No extra work order: `docs/ONPREM_COMPOSE.md`.

## Integration gap closed in code

SOW, Plan Generator, WSR, and Retrospective APIs persist jobs on disk and call ingestion, AI, and MPXJ. WSR and Retrospective dashboards are wired to those APIs.

## Recommended new work orders (if missing in Factory)

None. WO-34 runbook covers host sign-off of port 80 and `ONPREM_DATA_DIR`.

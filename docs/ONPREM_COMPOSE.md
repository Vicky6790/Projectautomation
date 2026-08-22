# On-premise Compose verification (WO-34)

This is the engineer runbook for **WO-34**. Local Windows Compose (WO-16–19, WO-33) is already proven. This overlay adds `AUTH_MODE=required`, a persistent host data directory, and the published client port.

## Start

```powershell
$env:AUTH_BOOTSTRAP_PASSWORD = "<host-only-secret>"
$env:ONPREM_HTTP_PORT = "80"
$env:ONPREM_DATA_DIR = "C:\ProgramData\project-automation"
docker compose -f docker-compose.yml -f docker-compose.onprem.yml up -d --build
```

Local rehearsal without binding port 80:

```powershell
$env:AUTH_BOOTSTRAP_PASSWORD = "onprem-verify"
$env:ONPREM_HTTP_PORT = "8080"
$env:ONPREM_DATA_DIR = "./onprem-data"
docker compose -f docker-compose.yml -f docker-compose.onprem.yml up -d --build
python scripts/verify_onprem.py
```

`AUTH_BOOTSTRAP_PASSWORD` is required. `/ready` returns `503 AUTH_NOT_BOOTSTRAPPED` until it is set, and the client will not become healthy.

## Checks

| Check | Expected |
|-------|----------|
| `/health` | `200`, `auth_required: true` |
| `/ready` | `200`, writable `DATA_DIR` |
| Unauthenticated `/api/v1/plan/library` | `401 AUTH_REQUIRED` |
| Sign-in + `/api/v1/auth/me` | bootstrap user, role `admin` |
| `/sow`, `/plan`, `/wsr`, `/retrospective` | SPA HTML |
| API `:8000` on the host | closed |
| Host `ONPREM_DATA_DIR` | survives `docker compose down` / `up` |
| Operator-owned plan handle | other identities get `404` |

Module E2E scripts (`verify_sow.py`, `verify_plan.py`, `verify_wsr.py`, `verify_retrospective.py`) now sign in when `auth_required` is true. Set `AUTH_BOOTSTRAP_PASSWORD` before running them against the overlay. Overlay default `AI_STUB=false` needs `OPENAI_API_KEY` for SOW/WSR/retrospective generation.

## Out of scope (already tracked)

SSO, TLS termination, monitoring, backups, and multi-server scaling.

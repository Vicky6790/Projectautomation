# Project Automation

Local MVP for SOW analysis, project-plan generation, weekly status reports, and retrospectives.

## Layout

| Path | Work order | Role |
|------|------------|------|
| `backend/` | WO-1 | FastAPI app, API Docker image (Python + JRE 17) |
| `frontend/` | WO-6 | React UI shell, nginx image with `/api` proxy |
| `docker-compose.yml` | WO-26 starter | Local Compose; on-prem runbook still WO-26 |
| `data/` | — | Uploads and job JSON (gitignored) |

## Local auth rule

- **Local MVP:** endpoints do **not** authenticate callers (`AUTH_MODE=disabled`).
- **On-prem multi-user:** set `AUTH_MODE=required` (adapter is a later work order).

Plan generation does **not** use a reference MPP. MPP files supplied by the user are validated later in WO-4.

## Run

Backend (Python 3.12):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

API docs: http://localhost:8000/docs

## Docker (preferred local path)

Requires Docker Desktop on Windows. The API is not published on the host; the browser uses the client on port 8080, which proxies `/api` and `/health`. Local Compose sets `AI_STUB=true` so SOW analysis can complete without an OpenAI key.

```powershell
docker compose up --build
```

App: http://localhost:8080

Verify the SOW path through the proxy:

```powershell
python scripts/verify_sow.py
```

Verify the Plan Generator path through the proxy (library → preview → approve → MSPDI download):

```powershell
python scripts/verify_plan.py
```

Verify the WSR path through the proxy (MPP upload → generate → nine-section report):

```powershell
python scripts/verify_wsr.py
```

On-premise overlay (host port 80, persistent data directory, stub off):

```powershell
docker compose -f docker-compose.yml -f docker-compose.onprem.yml up -d --build
```

## Tests

```powershell
cd backend
pytest
cd ..\frontend
npm run lint
npm run build
```

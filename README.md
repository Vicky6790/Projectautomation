# Project Automation

Local MVP for SOW analysis, project-plan generation, weekly status reports, and retrospectives.

## Layout

| Path | Work order | Role |
|------|------------|------|
| `backend/` | WO-1 | FastAPI app, shared contracts, local filesystem storage |
| `frontend/` | WO-6 | React + Vite UI shell |
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

## Tests

```powershell
cd backend
pytest
cd ..\frontend
npm run lint
npm run build
```

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "auth_mode": settings.auth_mode,
        "auth_required": settings.auth_required,
    }


@router.get("/ready")
def ready() -> JSONResponse:
    try:
        settings.ensure_storage()
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})
    return JSONResponse({"status": "ready", "data_dir": str(settings.data_dir.resolve())})

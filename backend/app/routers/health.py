from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.access import access
from app.config import settings
from app.errors import AppError

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
        if settings.auth_required:
            access.bootstrap()
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})
    except AppError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": exc.message, "code": exc.code},
        )
    return JSONResponse({"status": "ready", "data_dir": str(settings.data_dir.resolve())})

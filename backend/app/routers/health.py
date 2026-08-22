from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "auth_mode": settings.auth_mode,
        "auth_required": settings.auth_required,
    }

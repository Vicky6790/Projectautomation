from fastapi import APIRouter

from app.plan.library import catalog

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.get("/library")
def get_library() -> dict:
    return catalog()

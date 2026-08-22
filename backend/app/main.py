from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import AppError, register_exception_handlers
from app.routers import files, health, jobs, plan, sow
from app.storage import store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_storage()
    store.purge_expired()
    yield


def create_app() -> FastAPI:
    settings.ensure_storage()
    application = FastAPI(
        title="Project Automation API",
        version="0.1.0",
        description=(
            "Local MVP API. Auth is disabled unless AUTH_MODE=required. "
            "Module processing (ingestion, AI, MPP, export) is stubbed until later work orders."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(files.router)
    application.include_router(jobs.router)
    application.include_router(sow.router)
    application.include_router(plan.router)

    @application.middleware("http")
    async def auth_gate(request, call_next):
        if settings.auth_required and request.url.path not in {
            "/health",
            "/ready",
            "/docs",
            "/openapi.json",
        }:
            raise AppError(401, "AUTH_REQUIRED", "Authentication is required in this environment")
        return await call_next(request)

    return application


app = create_app()

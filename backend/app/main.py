import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.access import COOKIE_NAME, access, public_path
from app.config import settings
from app.context import current_operator_id, current_operator_role
from app.errors import AppError, error_body, register_exception_handlers
from app.routers import auth, files, health, jobs, plan, retrospective, sow, wsr
from app.storage import store

_HANDLE = re.compile(
    r"/api/v1/(?:sow|wsr|retrospective|plan|files|jobs)/([0-9a-f-]{36})",
    re.I,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_storage()
    store.purge_expired()
    if settings.auth_required:
        try:
            access.bootstrap()
        except AppError:
            pass
    yield


def create_app() -> FastAPI:
    settings.ensure_storage()
    application = FastAPI(
        title="Project Automation API",
        version="0.1.0",
        description=(
            "Local MVP API. AUTH_MODE=disabled skips sign-in. "
            "AUTH_MODE=required issues HttpOnly session cookies. "
            "Public routes are versioned under /api/v1. "
            "ProcessingResponse.status is queued|running|succeeded|failed "
            "(blueprint state processing|complete|failed). "
            "See docs/OPENAPI_FREEZE.md."
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
    application.include_router(auth.router)
    application.include_router(files.router)
    application.include_router(jobs.router)
    application.include_router(sow.router)
    application.include_router(wsr.router)
    application.include_router(retrospective.router)
    application.include_router(plan.router)

    @application.middleware("http")
    async def auth_gate(request: Request, call_next):
        if request.method == "OPTIONS" or public_path(request.url.path):
            return await call_next(request)
        operator = access.resolve_session(request.cookies.get(COOKIE_NAME))
        if settings.auth_required and operator is None:
            access.append_audit("refused", operator_id=None, handle=None, ok=False)
            return JSONResponse(
                status_code=401,
                content=error_body("AUTH_REQUIRED", "Sign-in is required"),
            )
        op_token = current_operator_id.set(operator.id if operator else None)
        role_token = current_operator_role.set(operator.role if operator else None)
        try:
            response = await call_next(request)
        finally:
            current_operator_id.reset(op_token)
            current_operator_role.reset(role_token)
        action = _audit_action(request.method, request.url.path)
        if action:
            match = _HANDLE.search(request.url.path)
            access.append_audit(
                action,
                operator_id=operator.id if operator else None,
                handle=match.group(1) if match else None,
                ok=200 <= response.status_code < 400,
            )
        return response

    return application


def _audit_action(method: str, path: str) -> str | None:
    if method == "POST" and (path.endswith("/uploads") or path.rstrip("/").endswith("/files")):
        return "upload"
    if path.endswith("/retry") and method == "POST":
        return "retry"
    if path.endswith("/report") or path.endswith("/mpp"):
        return "download"
    if method == "PATCH" and "/items/" in path:
        return "review"
    generate_tokens = ("analyze", "preview", "approve", "generate")
    if method == "POST" and any(token in path for token in generate_tokens):
        return "generate"
    return None


app = create_app()

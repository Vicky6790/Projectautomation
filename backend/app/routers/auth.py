from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.access import COOKIE_NAME, Operator, access
from app.config import settings
from app.context import current_operator_id, current_operator_role
from app.errors import AppError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SignInRequest(BaseModel):
    username: str
    password: str


class OperatorView(BaseModel):
    id: str
    username: str
    role: str
    enabled: bool = True


class CreateOperatorRequest(BaseModel):
    username: str
    password: str
    role: str = Field(default="operator")


def _view(operator: Operator) -> OperatorView:
    return OperatorView(
        id=operator.id,
        username=operator.username,
        role=operator.role,
        enabled=operator.enabled,
    )


def _admin() -> None:
    if current_operator_role.get() != "admin":
        raise AppError(403, "ADMIN_REQUIRED", "Administrator access is required")


@router.post("/login", response_model=OperatorView)
def login(body: SignInRequest, response: Response) -> OperatorView:
    try:
        operator = access.authenticate(body.username, body.password)
        session = access.create_session(operator)
        access.append_audit("login", operator_id=operator.id, handle=None, ok=True)
    except AppError:
        access.append_audit("login", operator_id=None, handle=None, ok=False)
        raise
    response.set_cookie(
        COOKIE_NAME,
        session.id,
        httponly=True,
        samesite="lax",
        max_age=settings.session_idle_hours * 3600,
    )
    return _view(operator)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    operator_id = current_operator_id.get()
    access.drop_session(request.cookies.get(COOKIE_NAME))
    access.append_audit("logout", operator_id=operator_id, handle=None, ok=True)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=OperatorView)
def me() -> OperatorView:
    operator_id = current_operator_id.get()
    if not operator_id:
        raise AppError(401, "AUTH_REQUIRED", "Sign-in is required")
    match = next((item for item in access.list_operators() if item.id == operator_id), None)
    if match is None:
        raise AppError(401, "AUTH_REQUIRED", "Sign-in is required")
    return _view(match)


@router.get("/users", response_model=list[OperatorView])
def list_users() -> list[OperatorView]:
    _admin()
    return [_view(item) for item in access.list_operators()]


@router.post("/users", response_model=OperatorView)
def create_user(body: CreateOperatorRequest) -> OperatorView:
    _admin()
    if body.role not in {"operator", "admin"}:
        raise AppError(400, "INVALID_ROLE", "Role must be operator or admin")
    operator = access.add_operator(body.username, body.password, body.role)  # type: ignore[arg-type]
    return _view(operator)


@router.post("/users/{operator_id}/disable", response_model=OperatorView)
def disable_user(operator_id: str) -> OperatorView:
    _admin()
    return _view(access.disable_operator(operator_id))

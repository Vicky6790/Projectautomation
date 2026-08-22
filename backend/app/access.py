from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.config import settings
from app.errors import AppError

Role = Literal["operator", "admin"]
COOKIE_NAME = "pa_session"
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class Operator(BaseModel):
    id: str
    username: str
    password_hash: str
    role: Role = "operator"
    enabled: bool = True


class Session(BaseModel):
    id: str
    operator_id: str
    last_seen: datetime


class OperatorStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        path = Path(self._root or settings.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def users_path(self) -> Path:
        return self.root / "users.json"

    def sessions_path(self) -> Path:
        return self.root / "sessions.json"

    def audit_path(self) -> Path:
        return self.root / "audit.jsonl"

    def bootstrap(self) -> None:
        users = self._load_users()
        if users:
            return
        password = settings.auth_bootstrap_password
        if not settings.auth_required:
            return
        if not password:
            raise AppError(
                503,
                "AUTH_NOT_BOOTSTRAPPED",
                "AUTH_BOOTSTRAP_PASSWORD is required when AUTH_MODE=required",
            )
        users.append(
            Operator(
                id=str(uuid.uuid4()),
                username=settings.auth_bootstrap_user,
                password_hash=_hash_secret(password),
                role="admin",
            )
        )
        self._save_users(users)

    def authenticate(self, username: str, password: str) -> Operator:
        operator = next((item for item in self._load_users() if item.username == username), None)
        if operator is None or not operator.enabled:
            raise AppError(401, "AUTH_FAILED", "Sign-in failed")
        if not _verify_secret(password, operator.password_hash):
            raise AppError(401, "AUTH_FAILED", "Sign-in failed")
        return operator

    def create_session(self, operator: Operator) -> Session:
        session = Session(id=secrets.token_urlsafe(32), operator_id=operator.id, last_seen=_now())
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session

    def resolve_session(self, session_id: str | None) -> Operator | None:
        if not session_id:
            return None
        idle = timedelta(hours=settings.session_idle_hours)
        sessions = []
        found: Session | None = None
        now = _now()
        for session in self._load_sessions():
            last = session.last_seen
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if now - last > idle:
                continue
            if session.id == session_id:
                session.last_seen = now
                found = session
            sessions.append(session)
        self._save_sessions(sessions)
        if found is None:
            return None
        operator = next((item for item in self._load_users() if item.id == found.operator_id), None)
        if operator is None or not operator.enabled:
            return None
        return operator

    def drop_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        sessions = [item for item in self._load_sessions() if item.id != session_id]
        self._save_sessions(sessions)

    def drop_operator_sessions(self, operator_id: str) -> None:
        sessions = [item for item in self._load_sessions() if item.operator_id != operator_id]
        self._save_sessions(sessions)

    def list_operators(self) -> list[Operator]:
        return self._load_users()

    def add_operator(self, username: str, password: str, role: Role) -> Operator:
        users = self._load_users()
        if any(item.username == username for item in users):
            raise AppError(409, "USER_EXISTS", "That identity is already in use")
        operator = Operator(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=_hash_secret(password),
            role=role,
        )
        users.append(operator)
        self._save_users(users)
        return operator

    def disable_operator(self, operator_id: str) -> Operator:
        users = self._load_users()
        match = next((item for item in users if item.id == operator_id), None)
        if match is None:
            raise AppError(404, "USER_NOT_FOUND", "Operator was not found")
        match.enabled = False
        self._save_users(users)
        self.drop_operator_sessions(operator_id)
        return match

    def append_audit(
        self,
        action: str,
        *,
        operator_id: str | None,
        handle: str | None,
        ok: bool,
    ) -> None:
        record = {
            "at": _now().isoformat(),
            "action": action,
            "operator_id": operator_id,
            "handle": handle,
            "ok": ok,
        }
        with self.audit_path().open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")

    def _load_users(self) -> list[Operator]:
        path = self.users_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Operator.model_validate(item) for item in payload.get("users", [])]

    def _save_users(self, users: list[Operator]) -> None:
        self.users_path().write_text(
            json.dumps({"users": [item.model_dump() for item in users]}, indent=2),
            encoding="utf-8",
        )

    def _load_sessions(self) -> list[Session]:
        path = self.sessions_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Session.model_validate(item) for item in payload.get("sessions", [])]

    def _save_sessions(self, sessions: list[Session]) -> None:
        self.sessions_path().write_text(
            json.dumps({"sessions": [item.model_dump(mode="json") for item in sessions]}, indent=2),
            encoding="utf-8",
        )


def public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path == "/api/v1/auth/login"


def _hash_secret(secret: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), 120_000)
    return f"{salt}${digest.hex()}"


def _verify_secret(secret: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), 120_000).hex()
    return secrets.compare_digest(check, digest)


def _now() -> datetime:
    return datetime.now(UTC)


access = OperatorStore()

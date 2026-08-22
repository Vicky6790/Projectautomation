from pathlib import Path

from app.config import settings
from app.errors import AppError
from app.ingestion.policy import UploadPolicy, policy_for
from app.models import Module


def looks_like_project_file(content: bytes) -> bool:
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        return True
    if content.startswith(b"PK"):
        return True
    head = content.lstrip()[:256].lower()
    if head.startswith(b"mpx") or head.startswith(b"<?xml") or b"<project" in head:
        return True
    return False


def format_size_limit(max_bytes: int) -> str:
    mega = 1024 * 1024
    if max_bytes >= mega and max_bytes % mega == 0:
        return f"{max_bytes // mega} MB"
    if max_bytes >= 1024:
        return f"{max_bytes / 1024:.1f} KB"
    return f"{max_bytes} bytes"


def validate_upload(filename: str, content: bytes, module: Module | None) -> UploadPolicy:
    if not content:
        raise AppError(400, "EMPTY_FILE", "Uploaded file is empty")
    policy = policy_for(module, filename)
    ext = Path(filename).suffix.lower()
    if ext not in policy.extensions:
        raise AppError(
            400,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type. Accepted formats: {policy.format_label}",
        )
    if policy.kind == "mpp" and not looks_like_project_file(content):
        raise AppError(
            400,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type. Accepted formats: {policy.format_label}",
        )
    limit = min(policy.max_bytes, settings.max_upload_bytes)
    if len(content) > limit:
        raise AppError(
            400,
            "FILE_TOO_LARGE",
            f"File exceeds the {format_size_limit(limit)} upload limit",
        )
    return policy

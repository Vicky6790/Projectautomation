from pathlib import Path

from app.errors import AppError
from app.ingestion.policy import UploadPolicy, policy_for
from app.models import Module


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
    if len(content) > policy.max_bytes:
        limit_mb = policy.max_bytes // (1024 * 1024)
        raise AppError(
            400,
            "FILE_TOO_LARGE",
            f"File exceeds the {limit_mb} MB upload limit",
        )
    return policy

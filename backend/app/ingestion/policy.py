from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError
from app.models import Module

SOW_MAX_BYTES = 25 * 1024 * 1024
MPP_MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class UploadPolicy:
    kind: str
    extensions: frozenset[str]
    max_bytes: int
    format_label: str


SOW_POLICY = UploadPolicy(
    kind="sow",
    extensions=frozenset({".pdf", ".docx"}),
    max_bytes=SOW_MAX_BYTES,
    format_label="PDF (.pdf) and Word (.docx)",
)

MPP_POLICY = UploadPolicy(
    kind="mpp",
    extensions=frozenset({".mpp"}),
    max_bytes=MPP_MAX_BYTES,
    format_label="Microsoft Project (.mpp)",
)


def policy_for(module: Module | None, filename: str) -> UploadPolicy:
    if module == "plan":
        raise AppError(
            400,
            "UPLOAD_NOT_APPLICABLE",
            "The plan generator does not accept a file upload",
        )
    if module == "sow":
        return SOW_POLICY
    if module in {"wsr", "retrospective"}:
        return MPP_POLICY
    ext = Path(filename).suffix.lower()
    if ext in SOW_POLICY.extensions:
        return SOW_POLICY
    if ext in MPP_POLICY.extensions:
        return MPP_POLICY
    raise AppError(
        400,
        "UNSUPPORTED_FILE_TYPE",
        "Unsupported file type. Accepted formats: PDF (.pdf), Word (.docx), "
        "Microsoft Project (.mpp)",
    )

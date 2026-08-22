from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.errors import AppError
from app.models import FileRecord, Module
from app.storage import store

router = APIRouter(prefix="/api/v1/files", tags=["files"])

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-project",
    "application/octet-stream",
    "text/plain",
}


@router.post("", response_model=FileRecord)
async def upload_file(
    file: UploadFile = File(...),
    module: Module | None = Form(default=None),
) -> FileRecord:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", f"Type {content_type} is not allowed")
    content = await file.read()
    if not content:
        raise AppError(400, "EMPTY_FILE", "Uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise AppError(
            400,
            "FILE_TOO_LARGE",
            f"File exceeds the {limit_mb:g} MB upload limit",
        )
    return store.save_upload(file.filename or "upload", content, content_type, module)


@router.get("/{file_id}")
def get_file_meta(file_id: str) -> FileRecord:
    record, _ = store.get_file(file_id)
    return record


@router.get("/{file_id}/download")
def download_file(file_id: str) -> FileResponse:
    record, path = store.get_file(file_id)
    return FileResponse(
        path,
        filename=record.filename,
        media_type=record.content_type,
    )

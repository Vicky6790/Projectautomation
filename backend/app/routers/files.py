from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.errors import AppError
from app.ingestion import extract_sow_text, validate_upload
from app.models import FileRecord, Module
from app.storage import store

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("", response_model=FileRecord)
async def upload_file(
    file: UploadFile = File(...),
    module: Module | None = Form(default=None),
) -> FileRecord:
    filename = file.filename or "upload"
    content = await file.read()
    policy = validate_upload(filename, content, module)
    extracted = extract_sow_text(filename, content) if policy.kind == "sow" else None
    content_type = file.content_type or "application/octet-stream"
    return store.save_upload(filename, content, content_type, module, extracted_text=extracted)


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


@router.get("/{file_id}/text")
def get_extracted_text(file_id: str) -> dict:
    record, _ = store.get_file(file_id)
    text_path = store.uploads / f"{file_id}.txt"
    if not record.extracted_text_available or not text_path.exists():
        raise AppError(404, "TEXT_NOT_FOUND", "No extracted text is available for this file")
    text = text_path.read_text(encoding="utf-8")
    return {"file_id": file_id, "char_count": len(text), "text": text}

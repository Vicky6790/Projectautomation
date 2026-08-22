from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Module = Literal["sow", "wsr", "retrospective", "plan"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class ApiError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ProcessingResponse(BaseModel):
    id: str
    module: Module
    status: JobStatus
    file_id: str | None = None
    result: dict[str, Any] | None = None
    error: ApiError | None = None
    created_at: datetime
    updated_at: datetime


class FileRecord(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    module: Module | None = None
    extracted_text_available: bool = False
    extracted_char_count: int | None = None
    created_at: datetime


class StartJobRequest(BaseModel):
    file_id: str = Field(min_length=1)


class ProjectPlanData(BaseModel):
    """Retrospective-ready plan snapshot. Metrics are owned by analysis, not MPP."""

    name: str
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    planned_only: bool = True
    metrics: dict[str, Any] = Field(default_factory=dict)


class RetrospectiveReport(BaseModel):
    summary: str
    findings: list[str] = Field(default_factory=list)
    plan: ProjectPlanData | None = None

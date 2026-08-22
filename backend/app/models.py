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
    request_handle: str | None = None
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
    plan_available: bool = False
    created_at: datetime
    last_accessed_at: datetime | None = None


class StartJobRequest(BaseModel):
    file_id: str | None = None


class PlanTaskData(BaseModel):
    id: int
    name: str
    outline_level: int = 1
    is_summary: bool = False
    is_milestone: bool = False
    set_name: str | None = None
    baseline_start: str | None = None
    baseline_finish: str | None = None
    actual_start: str | None = None
    actual_finish: str | None = None
    percent_complete: float = 0
    predecessor_ids: list[int] = Field(default_factory=list)
    comparison_available: bool = False


class ProjectPlanData(BaseModel):
    """WSR/retrospective plan snapshot. Baseline values stay distinct from scheduled dates."""

    name: str
    status_date: str | None = None
    has_actuals: bool = False
    planned_only: bool = True
    tasks: list[PlanTaskData] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class GeneratedTask(BaseModel):
    id: int
    name: str
    outline_level: int = 1
    is_summary: bool = False
    is_milestone: bool = False
    set_name: str | None = None
    predecessor_ids: list[int] = Field(default_factory=list)


class GeneratedPlan(BaseModel):
    name: str
    tasks: list[GeneratedTask] = Field(default_factory=list)


class RetrospectiveReport(BaseModel):
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    schedule_variance: list[str] = Field(default_factory=list)
    milestone_delivery: list[str] = Field(default_factory=list)
    task_completion: list[str] = Field(default_factory=list)
    what_went_well: list[str] = Field(default_factory=list)
    what_went_poorly: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    planned_only: bool = False
    plan: ProjectPlanData | None = None


class AnalysisReport(BaseModel):
    request_handle: str | None = None
    gray_areas: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class StatusReport(BaseModel):
    request_handle: str | None = None
    project_health: str | None = None
    progress: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    management_attention: list[str] = Field(default_factory=list)
    decisions_required: list[str] = Field(default_factory=list)
    next_7_day_priorities: list[str] = Field(default_factory=list)

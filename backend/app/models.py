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
    owner_id: str | None = None
    created_at: datetime
    last_accessed_at: datetime | None = None


class StartJobRequest(BaseModel):
    file_id: str | None = None


class PlanAssignmentData(BaseModel):
    resource_id: int | None = None
    resource_name: str
    planned_work_hours: float | None = None
    actual_work_hours: float | None = None


class PlanResourceData(BaseModel):
    id: int
    name: str
    max_units: float | None = None


class PlanPhaseData(BaseModel):
    """Outline-level-1 summary task. Dates stay source values; WSR does not estimate."""

    id: int
    name: str
    scheduled_start: str | None = None
    scheduled_finish: str | None = None
    baseline_start: str | None = None
    baseline_finish: str | None = None
    actual_start: str | None = None
    percent_complete: float = 0


class PlanTaskData(BaseModel):
    id: int
    name: str
    outline_level: int = 1
    is_summary: bool = False
    is_milestone: bool = False
    set_name: str | None = None
    gate: str | None = None
    baseline_start: str | None = None
    baseline_finish: str | None = None
    scheduled_start: str | None = None
    scheduled_finish: str | None = None
    actual_start: str | None = None
    actual_finish: str | None = None
    percent_complete: float = 0
    predecessor_ids: list[int] = Field(default_factory=list)
    predecessor_names: list[str] = Field(default_factory=list)
    comparison_available: bool = False
    planned_work_hours: float | None = None
    actual_work_hours: float | None = None
    assignments: list[PlanAssignmentData] = Field(default_factory=list)


class ProjectPlanData(BaseModel):
    """WSR/retrospective plan snapshot. Baseline values stay distinct from scheduled dates."""

    name: str
    owner: str | None = None
    status_date: str | None = None
    has_actuals: bool = False
    planned_only: bool = True
    tasks: list[PlanTaskData] = Field(default_factory=list)
    resources: list[PlanResourceData] = Field(default_factory=list)
    phases: list[PlanPhaseData] = Field(default_factory=list)
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


class EvidenceReference(BaseModel):
    task_or_milestone_name: str
    date: str | None = None
    progress: float | None = None
    predecessor_names: list[str] | None = None
    resource_assignments: list[str] | None = None
    dependency_description: str | None = None


class AiDerivedItem(BaseModel):
    id: str
    section: str
    content: str
    evidence_references: list[EvidenceReference] = Field(min_length=1)
    review_status: Literal["pending", "kept", "edited", "removed"] = "pending"


class NamedDateValue(BaseModel):
    name: str
    date: str | None = None


class PhaseStatus(BaseModel):
    name: str
    planned_start: str | None = None
    planned_finish: str | None = None
    progress: float | None = None
    state: Literal["not_started", "in_progress", "complete"]


class ProgressItem(BaseModel):
    name: str
    date: str | None = None
    progress: float | None = None


class MilestoneItem(BaseModel):
    name: str
    date: str | None = None


class WsrPlanFacts(BaseModel):
    project_name: str | None = None
    project_owner: str | None = None
    as_of_date: str
    generated_at: str
    project_health: Literal["on_track", "at_risk", "off_track", "unavailable"]
    countdown_days: int | None = None
    overall_progress: float | None = None
    planned_work_items: int | None = None
    completed_work_items: int | None = None
    capacity_utilization: float | None = None
    people_planned: int | None = None
    resources_deployed: int | None = None
    phase_count: int | None = None
    last_signed_off_milestone: NamedDateValue | None = None
    next_gate: NamedDateValue | None = None
    planned_go_live_date: str | None = None
    executive_overview: str | None = None
    timeline: list[PhaseStatus] | None = None
    phase_statuses: list[PhaseStatus] = Field(default_factory=list)
    progress_to_date: list[ProgressItem] = Field(default_factory=list)
    upcoming_milestones: list[MilestoneItem] = Field(default_factory=list)


class WsrItemDecision(BaseModel):
    decision: Literal["kept", "edited", "removed"]
    content: str | None = None


class WsrEvidenceResponse(BaseModel):
    item_id: str
    content: str
    section: str
    review_status: Literal["pending", "kept", "edited", "removed"]
    evidence_references: list[EvidenceReference]


class StatusReport(BaseModel):
    request_handle: str | None = None
    as_of_date: str | None = None
    generated_at: str | None = None
    planned_only: bool = False
    exportable: bool = False
    project_health: str | None = None
    facts: WsrPlanFacts | None = None
    progress: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    client_needs: list[AiDerivedItem] = Field(default_factory=list)
    risks: list[AiDerivedItem] = Field(default_factory=list)
    issues: list[AiDerivedItem] = Field(default_factory=list)
    dependencies: list[AiDerivedItem] = Field(default_factory=list)
    management_attention: list[AiDerivedItem] = Field(default_factory=list)
    decisions_required: list[AiDerivedItem] = Field(default_factory=list)
    next_7_day_priorities: list[AiDerivedItem] = Field(default_factory=list)

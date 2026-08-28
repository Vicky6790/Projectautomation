from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

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
    wbs: str | None = None
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


class SowFinding(BaseModel):
    category: str = ""
    priority: Literal["high", "medium", "low"] | None = None
    title: str
    description: str
    recommendation: str = ""


def _coerce_sow_findings(value: object, category: str) -> list[dict[str, object]]:
    if not value:
        return []
    if not isinstance(value, list):
        return value  # type: ignore[return-value]
    findings: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, str):
            findings.append(
                {
                    "category": category,
                    "title": item[:120],
                    "description": item,
                    "recommendation": "",
                }
            )
            continue
        if isinstance(item, dict):
            data = dict(item)
            data.setdefault("category", category)
            description = str(data.get("description") or data.get("title") or "")
            data.setdefault("title", description[:120] or "Finding")
            data.setdefault("description", description or str(data.get("title") or ""))
            data.setdefault("recommendation", "")
            findings.append(data)
            continue
        findings.append(item)  # type: ignore[arg-type]
    return findings


class AnalysisReport(BaseModel):
    request_handle: str | None = None
    processed_pages: int | None = None
    summary: str = ""
    gray_areas: list[SowFinding] = Field(default_factory=list)
    risks: list[SowFinding] = Field(default_factory=list)
    missing_requirements: list[SowFinding] = Field(default_factory=list)
    assumptions: list[SowFinding] = Field(default_factory=list)
    dependencies: list[SowFinding] = Field(default_factory=list)
    clarification_questions: list[SowFinding] = Field(default_factory=list)

    @field_validator(
        "gray_areas",
        "risks",
        "missing_requirements",
        "assumptions",
        "dependencies",
        "clarification_questions",
        mode="before",
    )
    @classmethod
    def coerce_findings(cls, value: object, info) -> object:
        return _coerce_sow_findings(value, info.field_name)


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
    """WSR phase row.

    planned_* comes from Baseline Start/Finish (planned end).
    actual_* holds the current Finish window used as the deviation date.
    """

    name: str
    wbs: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    actual_start: str | None = None
    actual_finish: str | None = None
    progress: float | None = None
    state: Literal["not_started", "in_progress", "complete"]


class DelayMappingRow(BaseModel):
    """One delayed phase or leaf task. Reason and mitigation stay empty unless present in the plan."""

    kind: Literal["phase", "task"]
    name: str
    parent_name: str | None = None
    wbs: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    revised_start: str | None = None
    revised_finish: str | None = None
    delay_days: int | None = None
    primary_reason: str | None = None
    go_live_impact: Literal["high", "medium"] | None = None
    mitigation_plan: str | None = None
    owner: str | None = None


class DelayMappingSheet(BaseModel):
    total_delayed_days: int = 0
    delayed_task_count: int = 0
    rows: list[DelayMappingRow] = Field(default_factory=list)


class ProgressItem(BaseModel):
    name: str
    date: str | None = None
    scheduled_start: str | None = None
    scheduled_finish: str | None = None
    progress: float | None = None


class MilestoneItem(BaseModel):
    name: str
    date: str | None = None
    scheduled_start: str | None = None
    scheduled_finish: str | None = None


class ExecutiveHighlight(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: str
    source_type: Literal["mpp", "calculation", "risk-engine"] = Field(
        validation_alias=AliasChoices("source_type", "sourceType"),
    )


class ExecutiveFocusItem(BaseModel):
    title: str
    description: str


class ExecutiveRiskItem(BaseModel):
    title: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]


class ExecutiveAction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: str
    reason: str
    source_type: Literal["ai-recommendation"] = Field(
        default="ai-recommendation",
        validation_alias=AliasChoices("source_type", "sourceType"),
    )

    @field_validator("source_type", mode="before")
    @classmethod
    def _recommendation_source(cls, value: object) -> str:
        return "ai-recommendation"


class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: str
    highlights: list[ExecutiveHighlight] = Field(default_factory=list)
    current_focus: list[ExecutiveFocusItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("current_focus", "currentFocus"),
    )
    executive_risks: list[ExecutiveRiskItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("executive_risks", "executiveRisks"),
    )
    recommended_actions: list[ExecutiveAction] = Field(
        default_factory=list,
        validation_alias=AliasChoices("recommended_actions", "recommendedActions"),
    )


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
    person_days_planned: float | None = None
    phase_count: int | None = None
    last_signed_off_milestone: NamedDateValue | None = None
    next_gate: NamedDateValue | None = None
    planned_go_live_date: str | None = None
    executive_overview: str | None = None
    executive_summary: ExecutiveSummary | None = None
    timeline: list[PhaseStatus] | None = None
    phase_statuses: list[PhaseStatus] = Field(default_factory=list)
    delay_mapping: DelayMappingSheet | None = None
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

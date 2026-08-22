from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.ai.client import OpenAiClient
from app.ai.criteria import RETRO_CRITERIA, SOW_CRITERIA, WSR_CRITERIA
from app.config import settings
from app.errors import AppError
from app.models import AnalysisReport, RetrospectiveReport, StatusReport

_client = OpenAiClient()

_SOW_LISTS = (
    "gray_areas",
    "risks",
    "missing_requirements",
    "assumptions",
    "dependencies",
    "clarification_questions",
)
_WSR_LISTS = (
    "progress",
    "milestones",
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
)
_RETRO_LISTS = (
    "schedule_variance",
    "milestone_delivery",
    "task_completion",
    "what_went_well",
    "what_went_poorly",
    "lessons_learned",
    "recommendations",
)


def analyze_sow(sow_text: str) -> AnalysisReport:
    if settings.ai_stub:
        snippet = sow_text.strip()[:80] or "uploaded SOW"
        return AnalysisReport(
            gray_areas=[f"[stub] Review undefined terms in: {snippet}"],
            risks=[],
            missing_requirements=[],
            assumptions=[],
            dependencies=[],
            clarification_questions=[],
        )
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO analyst. Return JSON only with keys gray_areas, risks, "
            "missing_requirements, assumptions, dependencies, clarification_questions. "
            "Each value is an array of strings. " + SOW_CRITERIA
        ),
        user_prompt=sow_text,
    )
    return _report(AnalysisReport, parsed, _SOW_LISTS)


def analyze_wsr(plan_data: dict[str, Any]) -> StatusReport:
    as_of = plan_data.get("as_of_date")
    metrics = plan_data.get("metrics") or {}
    planned_only = bool(plan_data.get("planned_only", True))
    if settings.ai_stub:
        overdue = int(metrics.get("overdue_count") or 0)
        health = "on_track" if overdue == 0 else "at_risk"
        return StatusReport(
            as_of_date=as_of,
            planned_only=planned_only,
            project_health=health,
            progress=list(metrics.get("progress_notes") or []),
            milestones=list(metrics.get("milestone_notes") or []),
            next_7_day_priorities=list(metrics.get("next_7_day_names") or []),
        )
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO status analyst. Return JSON only with keys project_health, "
            "progress, milestones, risks, issues, dependencies, management_attention, "
            "decisions_required, next_7_day_priorities. project_health is a string; "
            "the rest are arrays of strings. Measure progress and next_7_day_priorities "
            "from as_of_date. " + WSR_CRITERIA
        ),
        user_prompt=json.dumps(outbound_plan_summary(plan_data)),
    )
    report = _report(StatusReport, parsed, _WSR_LISTS)
    if not report.as_of_date:
        report.as_of_date = as_of
    report.planned_only = planned_only
    return report


def analyze_retrospective(plan_data: dict[str, Any]) -> RetrospectiveReport:
    metrics = plan_data.get("metrics") or {}
    planned_only = bool(plan_data.get("planned_only", True))
    if settings.ai_stub:
        return RetrospectiveReport(
            summary=(
                "[stub] Planned-only retrospective"
                if planned_only
                else "[stub] Planned-versus-actual retrospective"
            ),
            planned_only=planned_only,
            schedule_variance=list(metrics.get("schedule_notes") or []),
            milestone_delivery=list(metrics.get("milestone_notes") or []),
            task_completion=list(metrics.get("completion_notes") or []),
            what_went_well=list(metrics.get("on_time_names") or []),
            what_went_poorly=list(metrics.get("slipped_names") or []),
        )
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO retrospective analyst. Return JSON only with keys summary, "
            "schedule_variance, milestone_delivery, task_completion, what_went_well, "
            "what_went_poorly, lessons_learned, recommendations, planned_only. "
            "planned_only is boolean; summary is a string; other keys are arrays of strings. "
            + RETRO_CRITERIA
        ),
        user_prompt=json.dumps(outbound_plan_summary(plan_data)),
    )
    report = _report(RetrospectiveReport, parsed, _RETRO_LISTS)
    report.planned_only = planned_only
    return report


def outbound_plan_summary(plan_data: dict[str, Any]) -> dict[str, Any]:
    """WO-28: send MPP-derived summaries only, never the full task dump or raw files."""
    return {
        "as_of_date": plan_data.get("as_of_date"),
        "status_date": plan_data.get("status_date"),
        "planned_only": bool(plan_data.get("planned_only", True)),
        "task_count": len(plan_data.get("tasks") or []),
        "metrics": plan_data.get("metrics") or {},
    }


def _report(model: type, parsed: dict[str, Any], list_keys: tuple[str, ...]):
    normalized = dict(parsed)
    for key in list_keys:
        value = normalized.get(key, [])
        if value is None:
            normalized[key] = []
    try:
        return model.model_validate(normalized)
    except ValidationError as exc:
        raise AppError(
            502,
            "AI_PARSE_FAILED",
            "The AI response did not match the report schema",
            retryable=True,
        ) from exc

from __future__ import annotations

import json
from typing import Any

from app.ai.client import OpenAiClient
from app.ai.criteria import RETRO_CRITERIA, SOW_CRITERIA, WSR_CRITERIA
from app.config import settings
from app.models import AnalysisReport, RetrospectiveReport, StatusReport

_client = OpenAiClient()


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
    return AnalysisReport.model_validate(parsed)


def analyze_wsr(plan_data: dict[str, Any]) -> StatusReport:
    as_of = plan_data.get("as_of_date")
    metrics = plan_data.get("metrics") or {}
    if settings.ai_stub:
        overdue = int(metrics.get("overdue_count") or 0)
        health = "on_track" if overdue == 0 else "at_risk"
        return StatusReport(
            as_of_date=as_of,
            planned_only=bool(plan_data.get("planned_only", True)),
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
        user_prompt=json.dumps(plan_data),
    )
    report = StatusReport.model_validate(parsed)
    if not report.as_of_date:
        report.as_of_date = as_of
    report.planned_only = bool(plan_data.get("planned_only", report.planned_only))
    return report


def analyze_retrospective(plan_data: dict[str, Any]) -> RetrospectiveReport:
    if settings.ai_stub:
        return RetrospectiveReport(summary="[stub] Planned-only retrospective", planned_only=True)
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO retrospective analyst. Return JSON only with keys summary, "
            "schedule_variance, milestone_delivery, task_completion, what_went_well, "
            "what_went_poorly, lessons_learned, recommendations, planned_only. "
            "planned_only is boolean; summary is a string; other keys are arrays of strings. "
            + RETRO_CRITERIA
        ),
        user_prompt=json.dumps(plan_data),
    )
    return RetrospectiveReport.model_validate(parsed)

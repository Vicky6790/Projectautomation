from __future__ import annotations

import json
from typing import Any

from app.ai.client import OpenAiClient
from app.ai.criteria import RETRO_CRITERIA, SOW_CRITERIA, WSR_CRITERIA
from app.models import AnalysisReport, RetrospectiveReport, StatusReport

_client = OpenAiClient()


def analyze_sow(sow_text: str) -> AnalysisReport:
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
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO status analyst. Return JSON only with keys project_health, "
            "progress, milestones, risks, issues, dependencies, management_attention, "
            "decisions_required, next_7_day_priorities. project_health is a string; "
            "the rest are arrays of strings. " + WSR_CRITERIA
        ),
        user_prompt=json.dumps(plan_data),
    )
    return StatusReport.model_validate(parsed)


def analyze_retrospective(plan_data: dict[str, Any]) -> RetrospectiveReport:
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

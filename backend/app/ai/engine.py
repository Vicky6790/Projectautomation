from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.ai.client import OpenAiClient
from app.ai.criteria import RETRO_CRITERIA, SOW_CRITERIA, WSR_CRITERIA
from app.config import settings
from app.errors import AppError
from app.models import AnalysisReport, RetrospectiveReport

_client = OpenAiClient()

_SOW_LISTS = (
    "gray_areas",
    "risks",
    "missing_requirements",
    "assumptions",
    "dependencies",
    "clarification_questions",
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
            gray_areas=[
                {
                    "category": "gray_areas",
                    "priority": "medium",
                    "title": "Undefined delivery language",
                    "description": f"Review undefined terms in: {snippet}",
                    "recommendation": "Replace vague wording with measurable acceptance criteria.",
                }
            ],
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
            "Each value is an array of objects with priority (high, medium, or low), "
            "title, description, and recommendation. Do not invent facts. " + SOW_CRITERIA
        ),
        user_prompt=sow_text,
    )
    return _report(AnalysisReport, parsed, _SOW_LISTS)


def analyze_wsr(plan_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    from app.wsr.evidence import AI_SECTIONS, resolve_item

    plan = _plan_from_payload(plan_data)
    if settings.ai_stub:
        return _stub_wsr_items(plan, plan_data.get("as_of_date") or "")
    parsed = _client.complete_json(
        system_prompt=(
            "You are a PMO status analyst. Return JSON only with keys client_needs, "
            "risks, issues, dependencies, management_attention, decisions_required, "
            "next_7_day_priorities. Each value is an array of objects with content "
            "(string) and evidence_names (array of plan task names from the catalog). "
            "Do not set project health or invent tasks. Omit an item that has no "
            "catalog evidence. " + WSR_CRITERIA
        ),
        user_prompt=json.dumps(outbound_wsr_payload(plan_data)),
    )
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in AI_SECTIONS}
    for key in AI_SECTIONS:
        raw_items = parsed.get(key) or []
        if not isinstance(raw_items, list):
            raise AppError(
                502,
                "AI_PARSE_FAILED",
                "The AI response did not match the report schema",
                retryable=True,
            )
        for raw in raw_items:
            if isinstance(raw, str):
                names: list[str] = []
                content = raw
            elif isinstance(raw, dict):
                content = str(raw.get("content") or "")
                names = [str(name) for name in (raw.get("evidence_names") or []) if name]
            else:
                continue
            item = resolve_item(plan, key, content, names)
            if item is not None:
                grouped[key].append(item.model_dump())
    return grouped


def _stub_wsr_items(plan, as_of: str) -> dict[str, list[dict[str, Any]]]:
    from app.wsr.evidence import AI_SECTIONS, resolve_item
    from app.wsr.facts import next_seven_day_tasks

    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in AI_SECTIONS}
    for task in next_seven_day_tasks(plan, as_of):
        item = resolve_item(plan, "next_7_day_priorities", f"Advance {task.name}", [task.name])
        if item is not None:
            grouped["next_7_day_priorities"].append(item.model_dump())
    return grouped


def outbound_wsr_payload(plan_data: dict[str, Any]) -> dict[str, Any]:
    from app.wsr.evidence import evidence_catalog

    plan = _plan_from_payload(plan_data)
    return {
        "as_of_date": plan_data.get("as_of_date"),
        "facts": plan_data.get("facts") or {},
        "evidence_catalog": evidence_catalog(plan),
    }


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


def _plan_from_payload(plan_data: dict[str, Any]):
    from app.models import ProjectPlanData

    raw = {key: value for key, value in plan_data.items() if key in ProjectPlanData.model_fields}
    raw.setdefault("name", "plan")
    return ProjectPlanData.model_validate(raw)


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

"""Generate, validate, and fall back an AI executive summary from intelligence data."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.ai.client import OpenAiClient
from app.config import settings
from app.errors import AppError
from app.models import (
    ExecutiveAction,
    ExecutiveFocusItem,
    ExecutiveHighlight,
    ExecutiveRiskItem,
    ExecutiveSummary,
)

_client = OpenAiClient()

SYSTEM_PROMPT = """You are an Executive Project Management Analyst.

Generate a concise executive summary using ONLY the verified project information provided in the input.

Rules:

1. Never invent project facts.
2. Never invent dates.
3. Never invent stakeholders.
4. Never invent approvals or sign-offs.
5. Never invent task status.
6. Never invent reasons for delays.
7. Never assume a task is at risk without evidence.
8. Never convert duration into effort unless explicitly instructed.
9. Distinguish MPP-derived facts from AI-generated recommendations.
10. If required information is unavailable, omit the statement rather than guessing.
11. Consolidate related task-level issues into executive-level themes.
12. Prioritize Go-Live impact, critical-path impact and major schedule risks.
13. Use the As-of Date supplied in the input as the reporting date.
14. Do not use information outside the supplied project intelligence data.
15. Keep the summary concise and suitable for senior management.

Write in professional project-management language.

Do not use marketing language.

Do not exaggerate project health.

Return JSON only with this shape:
{
  "summary": "5-7 sentences, omit a sentence when the input lacks evidence",
  "highlights": [{"title": "", "description": "", "sourceType": "mpp|calculation|risk-engine"}],
  "currentFocus": [{"title": "", "description": ""}],
  "executiveRisks": [{"title": "", "description": "", "severity": "critical|high|medium|low"}],
  "recommendedActions": [{"action": "", "reason": "", "sourceType": "ai-recommendation"}]
}

Sentence guide for summary when evidence exists:
1. Project overview (name, owner if present, major phases).
2. Timeline (start date, planned Go-Live).
3. Overall work-based progress and important phase progress.
4. Current stage.
5. Key completed milestones — only with supplied evidence. Do not say signed off, approved, accepted, or presented unless evidence says so.
6. Immediate focus from upcoming milestones.
7. The most important consolidated risk, especially Go-Live impact.

Recommended actions are AI recommendations, not confirmed project decisions.
Do not mention a client, bank, or stakeholder unless that name appears in the input.
If progress.metric is unavailable, say progress is unavailable from plan data. Do not invent a percent.
"""


def generate_executive_summary(payload: dict[str, Any]) -> ExecutiveSummary:
    fallback = fallback_executive_summary(payload)
    if settings.ai_stub:
        return fallback
    try:
        parsed = _client.complete_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, default=str),
        )
    except AppError:
        return fallback
    validated = validate_executive_summary(parsed)
    return validated or fallback


def validate_executive_summary(raw: object) -> ExecutiveSummary | None:
    if not isinstance(raw, dict):
        return None
    try:
        summary = ExecutiveSummary.model_validate(raw)
    except ValidationError:
        return None
    text = " ".join(summary.summary.split()).strip()
    if not text:
        return None
    return summary.model_copy(update={"summary": text})


def fallback_executive_summary(payload: dict[str, Any]) -> ExecutiveSummary:
    project = payload.get("project") or {}
    progress = payload.get("progress") or {}
    phases = payload.get("phases") or []
    milestones = payload.get("milestones") or {}
    risks = payload.get("risks") or []
    health = payload.get("health") or {}
    sentences = _fallback_sentences(project, progress, phases, milestones, risks)
    highlights = _fallback_highlights(progress, phases, milestones)
    focus = _fallback_focus(phases, milestones)
    exec_risks = _fallback_risks(risks, health)
    actions = _fallback_actions(risks)
    return ExecutiveSummary(
        summary=" ".join(sentences),
        highlights=highlights,
        current_focus=focus,
        executive_risks=exec_risks,
        recommended_actions=actions,
    )


def _fallback_sentences(
    project: dict[str, Any],
    progress: dict[str, Any],
    phases: list[dict[str, Any]],
    milestones: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[str]:
    sentences: list[str] = []
    name = project.get("name") or "The project"
    phase_names = [phase.get("name") for phase in phases if phase.get("name")]
    relevant = _relevant_phases(phases)
    if phase_names:
        label = "phase" if len(phase_names) == 1 else "phases"
        span = (
            f", currently spanning {', '.join(item['name'] for item in relevant[:3])}."
            if relevant
            else "."
        )
        sentences.append(f"{name} covers {len(phase_names)} {label}{span}")
    else:
        sentences.append(f"{name} status is reported against the as-of date {project.get('asOfDate')}.")
    start = project.get("startDate")
    go_live = project.get("goLiveDate")
    timeline_bits: list[str] = []
    if start:
        timeline_bits.append(f"started {start}")
    if go_live:
        timeline_bits.append(f"with planned Go-Live {go_live}")
    if timeline_bits:
        sentences.append(f"The plan {_join_bits(timeline_bits)}.")
    if progress.get("metric") == "work" and progress.get("overallPercent") is not None:
        phase_bits = [
            f"{phase['name']} {phase['percentComplete']}%"
            for phase in relevant
            if phase.get("percentComplete") is not None
        ]
        extra = f", including {', '.join(phase_bits[:3])}" if phase_bits else ""
        sentences.append(
            f"Overall work-based progress is {progress['overallPercent']}% complete{extra}."
        )
    else:
        sentences.append("Overall work-based progress is unavailable from plan data.")
    current = _current_phase(phases)
    if current:
        sentences.append(f"The project is currently executing {current['name']}.")
    completed = (milestones.get("completed") or [])[:2]
    if completed:
        parts = []
        for item in completed:
            when = f" on {item['actualDate']}" if item.get("actualDate") else ""
            parts.append(f"{item['name']} completed{when}")
        sentences.append("Recently completed milestones: " + "; ".join(parts) + ".")
    upcoming = (milestones.get("upcoming") or [])[:3]
    if upcoming:
        names = ", ".join(item["name"] for item in upcoming)
        sentences.append(f"Immediate focus is {names}.")
    top = _top_risk(risks)
    if top:
        impact = " This can affect Go-Live." if top.get("goLiveImpact") else ""
        sentences.append(f"Principal risk: {top.get('title')}.{impact}".replace("..", "."))
    return sentences[:7]


def _fallback_highlights(
    progress: dict[str, Any],
    phases: list[dict[str, Any]],
    milestones: dict[str, Any],
) -> list[ExecutiveHighlight]:
    items: list[ExecutiveHighlight] = []
    if progress.get("metric") == "work" and progress.get("overallPercent") is not None:
        items.append(
            ExecutiveHighlight(
                title="Overall progress",
                description=f"{progress['overallPercent']}% complete based on actual work versus planned work.",
                source_type="calculation",
            )
        )
    else:
        items.append(
            ExecutiveHighlight(
                title="Overall progress",
                description="Progress unavailable from plan data",
                source_type="calculation",
            )
        )
    for phase in _relevant_phases(phases)[:4]:
        if phase.get("percentComplete") is None:
            continue
        items.append(
            ExecutiveHighlight(
                title=phase["name"],
                description=f"{phase['percentComplete']}% complete from leaf-task work.",
                source_type="calculation",
            )
        )
    for item in (milestones.get("completed") or [])[:2]:
        when = f" on {item['actualDate']}" if item.get("actualDate") else ""
        items.append(
            ExecutiveHighlight(
                title=item["name"],
                description=f"Completed{when}. {item.get('evidence') or ''}".strip(),
                source_type="mpp",
            )
        )
    return items


def _fallback_focus(
    phases: list[dict[str, Any]],
    milestones: dict[str, Any],
) -> list[ExecutiveFocusItem]:
    items: list[ExecutiveFocusItem] = []
    current = _current_phase(phases)
    if current:
        items.append(
            ExecutiveFocusItem(
                title=current["name"],
                description="Current executing phase based on incomplete leaf work and schedule window.",
            )
        )
    for item in (milestones.get("upcoming") or [])[:4]:
        due = f" due {item['plannedDate']}" if item.get("plannedDate") else ""
        items.append(
            ExecutiveFocusItem(
                title=item["name"],
                description=f"Upcoming milestone{due} ({item.get('daysToMilestone')} days from as-of).",
            )
        )
    return items


def _fallback_risks(
    risks: list[dict[str, Any]],
    health: dict[str, Any],
) -> list[ExecutiveRiskItem]:
    items: list[ExecutiveRiskItem] = []
    for risk in risks[:4]:
        evidence = risk.get("evidence") or []
        description = evidence[0] if evidence else risk.get("title") or ""
        if len(evidence) > 1:
            description = f"{description} {' '.join(evidence[1:3])}"
        items.append(
            ExecutiveRiskItem(
                title=risk.get("title") or "Risk",
                description=description,
                severity=_severity(risk.get("severity")),
            )
        )
    if not items and health.get("overall") in {"at-risk", "off-track"}:
        items.append(
            ExecutiveRiskItem(
                title="Schedule health",
                description=f"Overall health is {health.get('overall')} from plan calculations.",
                severity="high",
            )
        )
    return items


def _fallback_actions(risks: list[dict[str, Any]]) -> list[ExecutiveAction]:
    actions: list[ExecutiveAction] = []
    for risk in risks:
        mitigation = (risk.get("recommendedMitigation") or "").strip()
        if not mitigation:
            continue
        actions.append(
            ExecutiveAction(
                action=mitigation,
                reason=risk.get("title") or "Derived from the risk engine",
                source_type="ai-recommendation",
            )
        )
        if len(actions) >= 3:
            break
    return actions


def _relevant_phases(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [
        phase
        for phase in phases
        if phase.get("status") in {"at-risk", "off-track"}
        or (phase.get("percentComplete") not in (None, 0, 100))
    ]
    if ranked:
        return ranked
    return [phase for phase in phases if phase.get("percentComplete") not in (None, 0)][:3]


def _current_phase(phases: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = [
        phase
        for phase in phases
        if phase.get("status") in {"at-risk", "off-track", "on-track"}
        and phase.get("percentComplete") not in (None, 100)
    ]
    if active:
        return active[0]
    incomplete = [phase for phase in phases if phase.get("percentComplete") != 100]
    return incomplete[0] if incomplete else None


def _top_risk(risks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not risks:
        return None
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return min(risks, key=lambda item: (not item.get("goLiveImpact"), rank.get(item.get("severity"), 9)))


def _severity(value: object) -> str:
    if value in {"critical", "high", "medium", "low"}:
        return str(value)
    return "medium"


def _join_bits(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1]}"

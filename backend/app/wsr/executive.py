"""Generate, validate, and fall back an AI executive summary from intelligence data."""

from __future__ import annotations

import json
import re
from datetime import date
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

Create an AI-driven Executive Summary consisting of exactly 2 paragraphs from the supplied MPP analysis data.

Paragraph 1 — overall project position:
project/phase structure, overall work-based progress %, current active phase, major completed activities/sign-offs, and current delivery status.

Paragraph 2 — forward outlook:
current delivery focus, upcoming milestones, and Go-Live outlook. Keep the tone constructive and positive.

Rules:

1. Use only facts in the input. Never invent, estimate, or average data incorrectly.
2. Never invent dates, stakeholders, approvals, sign-offs, or task status.
3. Do not say signed off, approved, accepted, or presented unless the input evidence says so.
4. Never invent reasons for schedule movement.
5. Never assume a task needs recovery without evidence in risks, milestones, or delayMapping.
6. Never convert duration into effort.
7. Never calculate Go-Live dates, working days, delay duration, or delay attribution. You may summarize already-calculated delayMapping numbers only.
8. Use the As-of Date in project.asOfDate as the WSR reporting date.
9. If a metric is unavailable, omit it. Do not say a figure is unavailable.
10. Do not mention a client, bank, or stakeholder unless that name or ownerClass appears in the input.
11. Distinguish MPP-derived facts from recommendedActions (AI recommendations, not confirmed decisions).
12. Write in a concise, professional, constructive project-management tone suitable for senior management.
13. Do not use marketing language or exaggerate health.
14. Dynamically generate wording from the actual data. Do not copy placeholder brackets.
15. Do not use the words delay, delayed, delaying, behind, slip, slipped, overdue, off track, off-track, risk, or at risk. Do not say management attention, need action, or negative status language. Frame remaining work as current focus and next milestones.

Style for paragraph 1 when the facts exist:
"The project is progressing across X phases, with overall work-based progress at X%. The project is currently focused on [phase], with [key completed activity] completed and [current activity] underway." Include delivery status and the as-of date when those facts exist.

Style for paragraph 2 when the facts exist:
"Current delivery focus remains on [current workstream]. Next milestones include [names]. Go-Live remains on track based on the latest schedule and baseline comparison."
If Go-Live is not on track, say the team continues to advance Go-Live against the current schedule — do not describe it as behind or off track.
Never use the word "risk" or "at risk". Never repeat the same phase or task name in a sentence.

Keep the entire summary to exactly two well-written paragraphs. No bullets, headings, numbered lists, or additional commentary. Separate the paragraphs with a blank line.

Return JSON only with this shape:
{
  "summary": "paragraph 1\\n\\nparagraph 2",
  "highlights": [{"title": "", "description": "", "sourceType": "mpp|calculation|risk-engine"}],
  "currentFocus": [{"title": "", "description": ""}],
  "executiveRisks": [{"title": "", "description": "", "severity": "critical|high|medium|low"}],
  "recommendedActions": [{"action": "", "reason": "", "sourceType": "ai-recommendation"}]
}

If progress.metric is not "work" or overallPercent is missing, omit any progress percent.
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
    paragraphs = _split_paragraphs(summary.summary)
    if len(paragraphs) != 2:
        return None
    text = "\n\n".join(_scrub_summary_tone(part) for part in paragraphs)
    if _looks_like_list(text):
        return None
    if len(_split_paragraphs(text)) != 2:
        return None
    return summary.model_copy(update={"summary": text})


def fallback_executive_summary(payload: dict[str, Any]) -> ExecutiveSummary:
    project = payload.get("project") or {}
    progress = payload.get("progress") or {}
    phases = payload.get("phases") or []
    milestones = payload.get("milestones") or {}
    risks = payload.get("risks") or []
    health = payload.get("health") or {}
    delay = payload.get("delayMapping") or {}
    dependencies = payload.get("dependencies") or []
    paragraphs = _fallback_paragraphs(
        project,
        progress,
        phases,
        milestones,
        risks,
        health,
        delay if isinstance(delay, dict) else {},
        dependencies if isinstance(dependencies, list) else [],
    )
    highlights = _fallback_highlights(progress, phases, milestones)
    focus = _fallback_focus(phases, milestones)
    exec_risks = _fallback_risks(risks, health)
    actions = _fallback_actions(risks)
    return ExecutiveSummary(
        summary="\n\n".join(paragraphs),
        highlights=highlights,
        current_focus=focus,
        executive_risks=exec_risks,
        recommended_actions=actions,
    )


def _split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n+", (text or "").strip()) if part.strip()]


def _looks_like_list(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*([-*]|\d+[.)])\s+", text))


def _fallback_paragraphs(
    project: dict[str, Any],
    progress: dict[str, Any],
    phases: list[dict[str, Any]],
    milestones: dict[str, Any],
    risks: list[dict[str, Any]],
    health: dict[str, Any],
    delay: dict[str, Any],
    dependencies: list[dict[str, Any]],
) -> list[str]:
    return [
        _position_paragraph(project, progress, phases, milestones, health),
        _attention_paragraph(project, milestones, risks, health, delay, dependencies),
    ]


def _position_paragraph(
    project: dict[str, Any],
    progress: dict[str, Any],
    phases: list[dict[str, Any]],
    milestones: dict[str, Any],
    health: dict[str, Any],
) -> str:
    name = str(project.get("name") or "The project").strip() or "The project"
    phase_names = [phase.get("name") for phase in phases if phase.get("name")]
    count = project.get("phaseCount") if isinstance(project.get("phaseCount"), int) else len(phase_names)
    opening = f"{name} is progressing"
    if count:
        noun = "phase" if count == 1 else "phases"
        opening = f"{name} is progressing across {count} {noun}"
    if progress.get("metric") == "work" and progress.get("overallPercent") is not None:
        opening += f", with overall work-based progress at {_pct_text(progress['overallPercent'])}%"
    sentences = [opening + "."]
    current = _current_phase(phases)
    phase_name = None if current is None else str(current.get("name") or "").strip() or None
    completed = _unique_names(
        [
            str(item["name"]).strip()
            for item in (milestones.get("completed") or [])
            if item.get("name")
        ]
    )
    if phase_name:
        completed = [name for name in completed if not _covers(name, [phase_name])]
    completed = completed[:2]
    underway = _underway_name(milestones, current)
    if underway and _covers(underway, [name for name in (phase_name, *completed) if name]):
        underway = None
    focus = _focus_sentence(phase_name, completed, underway)
    if focus:
        sentences.append(focus)
    delivery = _delivery_sentence(project.get("asOfDate"), health.get("overall"))
    if delivery:
        sentences.append(delivery)
    return _scrub_summary_tone(" ".join(sentences))


def _focus_sentence(phase: str | None, completed: list[str], underway: str | None) -> str | None:
    extras: list[str] = []
    if completed:
        extras.append(f"{_join_and(completed)} completed")
    if underway:
        extras.append(f"{underway} underway")
    if phase:
        lead = f"Delivery is currently concentrated in {phase}"
        if not extras:
            return lead + "."
        if len(extras) == 1:
            return f"{lead}, with {extras[0]}."
        return f"{lead}, with {extras[0]} and {extras[1]}."
    if not extras:
        return None
    return f"The plan shows {(' and '.join(extras))}."


def _underway_name(milestones: dict[str, Any], current: dict[str, Any] | None) -> str | None:
    _ = current
    for item in milestones.get("upcoming") or []:
        name = str(item.get("name") or "").strip()
        if name:
            return name
    return None


def _delivery_sentence(as_of: object, health: object) -> str | None:
    as_of_text = _pretty_date(as_of)
    status = _health_phrase(health)
    if status and as_of_text:
        return f"As of {as_of_text}, delivery status is {status}."
    if status:
        return f"Delivery status is {status}."
    if as_of_text:
        return f"This assessment uses the WSR as-of date {as_of_text}."
    return None


def _attention_paragraph(
    project: dict[str, Any],
    milestones: dict[str, Any],
    risks: list[dict[str, Any]],
    health: dict[str, Any],
    delay: dict[str, Any],
    dependencies: list[dict[str, Any]],
) -> str:
    sentences: list[str] = []
    focus = _management_focus(risks, dependencies, delay)
    if focus:
        sentences.append(f"Current delivery focus remains on {focus}.")
    upcoming = _unique_names(
        [
            str(item["name"]).strip()
            for item in (milestones.get("upcoming") or [])
            if item.get("name")
        ]
    )[:3]
    if upcoming:
        if len(upcoming) == 1:
            sentences.append(f"The next milestone is {upcoming[0]}.")
        else:
            sentences.append(f"Next milestones include {_join_and(upcoming)}.")
    go_live = _go_live_sentence(health, delay)
    if go_live:
        sentences.append(go_live)
    if sentences:
        return _scrub_summary_tone(" ".join(sentences))
    as_of_text = _pretty_date(project.get("asOfDate"))
    if as_of_text:
        return _scrub_summary_tone(
            f"Delivery continues in line with the current plan as of {as_of_text}."
        )
    return _scrub_summary_tone("Delivery continues in line with the current plan.")


def _management_focus(
    risks: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    delay: dict[str, Any],
) -> str | None:
    top = _top_risk(risks)
    if top:
        names = _unique_names(
            [str(name).strip() for name in (top.get("affectedTasks") or []) if str(name).strip()]
        )
        if names:
            return names[0]
        title = _without_risk_word(str(top.get("title") or "").strip())
        if title:
            return title
    delayed = [item for item in dependencies if item.get("delayed")]
    if delayed:
        pred = str(delayed[0].get("predecessorName") or "").strip()
        succ = str(delayed[0].get("successorName") or "").strip()
        if pred and succ:
            return f"{pred}, which precedes {succ}"
        if pred:
            return pred
    for row in delay.get("rows") or []:
        if row.get("ownerClass") != "client" or row.get("taskType") not in {"delay", "additional"}:
            continue
        task = str(row.get("task") or "").strip()
        if task:
            return f"client-owned {task}"
    return None


def _attention_count(risks: list[dict[str, Any]], milestones: dict[str, Any]) -> int:
    names: list[str] = []
    for risk in risks:
        names.extend(str(name) for name in (risk.get("affectedTasks") or []) if name)
        if not risk.get("affectedTasks") and risk.get("title"):
            names.append(str(risk["title"]))
    names.extend(
        str(item["name"])
        for item in (milestones.get("overdue") or [])
        if item.get("name")
    )
    unique = list(dict.fromkeys(name.strip() for name in names if str(name).strip()))
    return len(unique)


def _impact_clause(risks: list[dict[str, Any]], delay: dict[str, Any]) -> str | None:
    shift = delay.get("actualShiftWorkingDays")
    if shift is None:
        shift = delay.get("netWorkingDayShift")
    if isinstance(shift, int) and shift > 0:
        return f"a {shift}-working-day Go-Live shift versus baseline"
    if any(risk.get("goLiveImpact") for risk in risks):
        return "Go-Live path impact"
    return None


def _go_live_sentence(health: dict[str, Any], delay: dict[str, Any]) -> str | None:
    status = _health_phrase(health.get("overall"))
    if not status:
        return None
    has_baseline = bool(delay.get("baselineGoLive") and delay.get("currentGoLive"))
    basis = (
        "based on the latest schedule and baseline comparison"
        if has_baseline
        else "based on the latest schedule"
    )
    if status == "on track":
        return f"Go-Live remains on track {basis}."
    return f"The team continues to advance Go-Live {basis}."


def _pct_text(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return str(number)


def _pretty_date(value: object) -> str | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        text = str(value).strip()
        return text or None
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def _health_phrase(value: object) -> str | None:
    raw = str(value or "").strip().replace("_", "-")
    return {
        "on-track": "on track",
        "at-risk": "progressing against the current baseline",
        "off-track": "being steered toward the agreed plan",
    }.get(raw)


def _name_key(value: str) -> str:
    return " ".join(value.lower().split())


def _unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        text = " ".join(str(name).split())
        key = _name_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _covers(candidate: str, existing: list[str]) -> bool:
    key = _name_key(candidate)
    if not key:
        return False
    for item in existing:
        other = _name_key(item)
        if not other:
            continue
        if key == other:
            return True
        if len(key) >= 6 and (key in other or other in key):
            return True
    return False


def _without_risk_word(value: str) -> str:
    text = re.sub(r"\bat[-\s]?risk\b", "", value, flags=re.IGNORECASE)
    text = re.sub(r"\brisks?\b", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip(" :-")


def _scrub_risk_word(text: str) -> str:
    cleaned = re.sub(
        r"\bat[-\s]?risk\b",
        "progressing against the current baseline",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\brisks?\b", "exposure", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _scrub_summary_tone(text: str) -> str:
    cleaned = _scrub_risk_word(text)
    replacements = (
        (
            r"\bno delayed items requiring management attention\b",
            "delivery continues in line with the current plan",
        ),
        (r"\bmanagement attention is on\b", "current delivery focus remains on"),
        (r"\b(\d+) plan items need action\b", r"\1 workstreams remain in progress"),
        (r"\b(\d+) plan item needs action\b", r"\1 workstream remains in progress"),
        (r"\bbehind the agreed baseline\b", "progressing against the current baseline"),
        (r"\boff track versus plan\b", "being steered toward the agreed plan"),
        (r"\boff[-\s]?track\b", "being steered toward the agreed plan"),
        (r"\bdelaying\b", "preceding"),
        (r"\bdelayed\b", "in progress"),
        (r"\boverdue\b", "upcoming"),
        (r"\bslipp?ed\b", "moved"),
    )
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _join_and(names: list[str]) -> str:
    cleaned = _unique_names(names)
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


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
                description=f"{phase['percentComplete']}% Work Complete from the plan.",
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





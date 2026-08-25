from __future__ import annotations

from app.errors import AppError
from app.models import AnalysisReport, Module, ProcessingResponse, RetrospectiveReport, StatusReport

SOW_SECTIONS = (
    ("gray_areas", "Gray areas"),
    ("risks", "Risks"),
    ("missing_requirements", "Missing requirements"),
    ("assumptions", "Assumptions"),
    ("dependencies", "Dependencies"),
    ("clarification_questions", "Clarification questions"),
)

WSR_SECTIONS = (
    ("executive_overview", "Executive Overview"),
    ("timeline", "Project Timeline"),
    ("phase_statuses", "Phase-Wise Status"),
    ("progress_to_date", "Progress to Date"),
    ("upcoming_milestones", "Upcoming Milestones"),
    ("client_needs", "What We Need From the Bank Team"),
    ("issues", "Issues"),
    ("dependencies", "Dependencies"),
    ("risks", "Risks & Focus Areas"),
    ("management_attention", "Management Attention"),
    ("decisions_required", "Decisions Required"),
    ("next_7_day_priorities", "Next Seven-Day Priorities"),
)

RETRO_SECTIONS = (
    ("schedule_variance", "Schedule variance"),
    ("milestone_delivery", "Milestone delivery"),
    ("task_completion", "Task completion"),
    ("what_went_well", "What went well"),
    ("what_went_poorly", "What went poorly"),
    ("lessons_learned", "Lessons learned"),
    ("recommendations", "Recommendations"),
)


_NOT_READY = {
    "sow": "Analysis must finish first before a report can be downloaded",
    "wsr": "Generation must finish first before a report can be downloaded",
    "retrospective": "Generation must finish first before a report can be downloaded",
}

_HEALTH_LABELS = {
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
    "unavailable": "Unavailable — insufficient plan data",
}

_EMPTY_AI = "No items identified from the plan"


def export_report(module: Module, job: ProcessingResponse) -> tuple[str, str, bytes]:
    if module == "plan":
        raise AppError(
            400,
            "REPORT_NOT_SUPPORTED",
            "Plan downloads are MPP files owned by MPP Processing",
        )
    if job.status != "succeeded" or not job.result:
        raise AppError(
            409,
            "EXPORT_NOT_READY",
            _NOT_READY.get(module, "Export is available only after processing has completed"),
        )
    handle = job.request_handle or job.id
    if module == "sow":
        payload = AnalysisReport.model_validate(job.result)
        body = _render("SOW analysis report", handle, SOW_SECTIONS, payload)
        filename = f"sow-analysis-{handle}.md"
    elif module == "wsr":
        payload = StatusReport.model_validate(job.result)
        body = _render_wsr(handle, payload)
        filename = f"wsr-report-{handle}.md"
    elif module == "retrospective":
        payload = RetrospectiveReport.model_validate(job.result)
        extra: list[str] = []
        if payload.summary:
            extra.append(f"Summary: {payload.summary}")
        extra.append(f"Planned only: {'yes' if payload.planned_only else 'no'}")
        body = _render("Project retrospective", handle, RETRO_SECTIONS, payload, extra)
        filename = f"retrospective-{handle}.md"
    else:
        raise AppError(400, "REPORT_NOT_SUPPORTED", f"No report export for module {module}")
    return filename, "text/markdown; charset=utf-8", body.encode("utf-8")


def _render(
    title: str,
    handle: str,
    sections: tuple,
    payload,
    extra: list[str] | None = None,
) -> str:
    lines = [f"# {title}", "", f"Request: `{handle}`", ""]
    if extra:
        lines.extend([*extra, ""])
    data = payload.model_dump()
    for key, heading in sections:
        lines.append(f"## {heading}")
        value = data.get(key)
        if value in (None, "", []):
            lines.append("Empty")
        elif isinstance(value, list):
            lines.extend(f"- {_one_line(item)}" for item in value)
        elif key == "project_health":
            lines.append(_HEALTH_LABELS.get(str(value), str(value)))
        else:
            lines.append(_one_line(value))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_wsr(handle: str, payload: StatusReport) -> str:
    facts = payload.facts
    health = (facts.project_health if facts else payload.project_health) or "unavailable"
    lines = [
        "# WSR & Insights",
        "",
        f"Request: `{handle}`",
        "",
        f"Project: {_unavailable(facts.project_name if facts else None)}",
        f"Owner: {_unavailable(facts.project_owner if facts else None)}",
        f"As of: {payload.as_of_date or _unavailable(None)}",
        f"Generated: {_unavailable(payload.generated_at)}",
        f"Project health: {_HEALTH_LABELS.get(str(health), str(health))}",
        "",
    ]
    data = facts.model_dump() if facts else {}
    for key, heading in WSR_SECTIONS:
        lines.append(f"## {heading}")
        if key in (
            "client_needs",
            "risks",
            "issues",
            "dependencies",
            "management_attention",
            "decisions_required",
            "next_7_day_priorities",
        ):
            items = getattr(payload, key)
            if not items:
                lines.append(_EMPTY_AI)
            else:
                for item in items:
                    if item.review_status == "removed":
                        continue
                    lines.append(f"- {item.content}")
                    source = item.evidence_references[0]
                    lines.append(f"  Source / Evidence: {source.task_or_milestone_name}")
        elif key == "executive_overview":
            lines.append(_unavailable(data.get("executive_overview")))
        elif key == "timeline":
            timeline = data.get("timeline")
            if not timeline:
                lines.append("A timeline cannot be generated")
            else:
                for phase in timeline:
                    start = phase.get("planned_start") or "Unavailable"
                    finish = phase.get("planned_finish") or "Unavailable"
                    lines.append(f"- {phase.get('name')}: {start} – {finish}")
        elif key == "phase_statuses":
            phases = data.get("phase_statuses") or []
            if not phases:
                lines.append(_unavailable(None))
            else:
                for phase in phases:
                    state = str(phase.get("state") or "").replace("_", " ")
                    lines.append(f"- {phase.get('name')}: {state}")
        elif key == "progress_to_date":
            items = data.get("progress_to_date") or []
            if not items:
                lines.append(_unavailable(None))
            else:
                lines.extend(f"- {item.get('name')}" for item in items)
        elif key == "upcoming_milestones":
            items = data.get("upcoming_milestones") or []
            if not items:
                lines.append("No upcoming milestone was identified")
            else:
                lines.extend(
                    f"- {item.get('name')}: {item.get('date') or 'Unavailable'}"
                    for item in items
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _unavailable(value: object) -> str:
    if value in (None, "", []):
        return "Unavailable"
    return _one_line(value)


def _one_line(value: object) -> str:
    return " ".join(str(value).split())

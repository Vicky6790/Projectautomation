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
    ("project_health", "Project health"),
    ("progress", "Progress"),
    ("milestones", "Milestones"),
    ("risks", "Risks"),
    ("issues", "Issues"),
    ("dependencies", "Dependencies"),
    ("management_attention", "Management attention"),
    ("decisions_required", "Decisions required"),
    ("next_7_day_priorities", "Next 7-day priorities"),
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
}


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
        extra = []
        if payload.as_of_date:
            extra.append(f"As of: {payload.as_of_date}")
        extra.append(f"Planned only: {'yes' if payload.planned_only else 'no'}")
        body = _render("Weekly status report", handle, WSR_SECTIONS, payload, extra)
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


def _one_line(value: object) -> str:
    return " ".join(str(value).split())

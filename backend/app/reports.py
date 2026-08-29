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
    ("executive_overview", "Executive Summary"),
    ("timeline", "Project Timeline"),
    ("phase_statuses", "Phase-Wise Status"),
    ("delay_mapping", "Go-Live Delay Mapping"),
    ("progress_to_date", "Progress of current week"),
    ("upcoming_milestones", "Upcoming Milestones Of Next Week"),
    ("risks", "Risks & Focus Areas"),
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


def export_report(
    module: Module,
    job: ProcessingResponse,
    scope: str | None = None,
) -> tuple[str, str, bytes]:
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
        extra = []
        extra.append(f"Summary: {payload.summary}" if payload.summary else "Summary: Analysis complete.")
        if payload.processed_pages is not None:
            extra.append(f"Processed pages: {payload.processed_pages}")
        body = _render("SOW analysis report", handle, SOW_SECTIONS, payload, extra)
        return f"sow-analysis-{handle}.md", "text/markdown; charset=utf-8", body.encode("utf-8")
    if module == "wsr":
        from app.wsr.pdf import render_delay_mapping_pdf, render_wsr_pdf

        payload = StatusReport.model_validate(job.result)
        if (scope or "").strip().casefold() == "delay_mapping":
            return (
                f"delay-mapping-{handle}.pdf",
                "application/pdf",
                render_delay_mapping_pdf(handle, payload),
            )
        return f"wsr-report-{handle}.pdf", "application/pdf", render_wsr_pdf(handle, payload)
    if module == "retrospective":
        payload = RetrospectiveReport.model_validate(job.result)
        extra: list[str] = []
        if payload.summary:
            extra.append(f"Summary: {payload.summary}")
        extra.append(f"Planned only: {'yes' if payload.planned_only else 'no'}")
        body = _render("Project retrospective", handle, RETRO_SECTIONS, payload, extra)
        return f"retrospective-{handle}.md", "text/markdown; charset=utf-8", body.encode("utf-8")
    raise AppError(400, "REPORT_NOT_SUPPORTED", f"No report export for module {module}")


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
    if isinstance(value, dict):
        title = str(value.get("title") or "").strip()
        description = str(value.get("description") or "").strip()
        recommendation = str(value.get("recommendation") or "").strip()
        priority = str(value.get("priority") or "").strip()
        parts = [part for part in (priority.title() if priority else "", title, description) if part]
        line = " — ".join(dict.fromkeys(parts))
        if recommendation:
            line = f"{line} Recommendation: {recommendation}" if line else f"Recommendation: {recommendation}"
        return " ".join(line.split())
    return " ".join(str(value).split())

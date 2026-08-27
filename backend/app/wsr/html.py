from __future__ import annotations

import html
from datetime import date, datetime

from app.models import (
    AiDerivedItem,
    StatusReport,
    WsrPlanFacts,
)

_AI_SECTIONS = (
    ("risks", "Risks & Focus Areas"),
)
_GANTT_COLORS = ("#475569", "#6366f1", "#10b981", "#8b5cf6", "#f59e0b")
_PHASE_STATE = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "complete": "Complete",
}


def render_wsr_html(handle: str, payload: StatusReport) -> str:
    facts = payload.facts or WsrPlanFacts(
        as_of_date=payload.as_of_date or "",
        generated_at=payload.generated_at or "",
        project_health=payload.project_health or "unavailable",
    )
    health = facts.project_health or payload.project_health or "unavailable"
    body = "".join(
        [
            _hero(payload, facts, health),
            _kpi_grid(facts),
            _section(1, "Executive Summary", _overview(facts)),
            _section(2, "Project Timeline", _timeline(facts)),
            _section(3, "Phase-Wise Status", _phases(facts)),
            _section(4, "Progress of current week", _progress(facts)),
            _section(5, "Upcoming milestone for Next Week", _milestones(facts, payload.as_of_date)),
            *[
                _section(index + 6, label, _insights(getattr(payload, key)))
                for index, (key, label) in enumerate(_AI_SECTIONS)
            ],
        ]
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>WSR &amp; Insights</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #334155; font-size: 10px; }}
h1 {{ font-size: 18px; margin: 0 0 8px; color: #1e293b; }}
h2 {{ font-size: 13px; margin: 0; color: #1e293b; }}
h3 {{ font-size: 12px; margin: 0 0 6px; }}
p {{ margin: 0 0 6px; }}
.muted {{ color: #64748b; }}
.card {{ border: 1px solid #e2e8f0; background: #ffffff; padding: 8px; }}
.hero td, .kpis td {{
  border: 1px solid #e2e8f0; background: #f8fafc; padding: 8px; vertical-align: top;
}}
.label {{ color: #64748b; font-size: 8px; }}
.value {{ font-size: 14px; font-weight: bold; color: #1e293b; }}
.countdown {{ font-size: 28px; font-weight: bold; color: #f43f5e; }}
.ring {{ font-size: 22px; font-weight: bold; text-align: center; }}
.num {{ color: #ffffff; background: #4f46e5; padding: 2px 6px; }}
.gantt {{ width: 100%; border-collapse: collapse; margin: 0 0 6px; }}
.gantt td {{ border: none; padding: 0; background: #ffffff; }}
.gantt-bar {{ height: 10px; }}
.badge {{ color: #4f46e5; font-weight: bold; }}
table {{ width: 100%; border-collapse: collapse; margin: 0 0 10px; }}
.section {{ margin: 0 0 12px; }}
</style>
</head>
<body>
<h1>WSR &amp; Insights</h1>
{body}
<p class="muted">Request: {html.escape(handle)}</p>
</body>
</html>
"""


def _hero(payload: StatusReport, facts: WsrPlanFacts, _health: str) -> str:
    countdown = (
        str(facts.countdown_days) if facts.countdown_days is not None else "Unavailable"
    )
    progress = _percent(facts.overall_progress)
    stamp = f"WSR Publish Date: {_short_date(payload.as_of_date)}"
    return f"""
<table class="hero">
<tr>
<td width="46%">
<h2>{_esc(facts.project_name)}</h2>
<p class="muted">{stamp}</p>
</td>
<td width="27%" align="center">
<p class="label">Countdown</p>
<p class="countdown">{html.escape(countdown)}</p>
<p class="muted">Days to Go-Live</p>
</td>
<td width="27%" align="center">
<p class="ring">{html.escape(progress if progress != "Unavailable" else "—")}</p>
<p class="muted">Overall Progress</p>
<p class="muted">By work completion</p>
</td>
</tr>
</table>
"""


def _kpi_grid(facts: WsrPlanFacts) -> str:
    work = _count(facts.completed_work_items)
    work_hint = (
        f"of {facts.planned_work_items} planned"
        if facts.planned_work_items is not None
        else "of planned work items"
    )
    deployed = facts.resources_deployed if facts.resources_deployed is not None else facts.people_planned
    cards = [
        ("Phases to Go-Live", _count(facts.phase_count), "Across project lifecycle"),
        ("Resources Deployed", _count(deployed), "From Resource Sheet"),
        ("Person-Days Planned", _person_days(facts.person_days_planned), "Total effort estimated"),
        ("Work Items Complete", work, work_hint),
    ]
    cells = "".join(
        f'<td width="25%"><p class="label">{html.escape(label)}</p>'
        f'<p class="value">{html.escape(value)}</p>'
        f'<p class="muted">{html.escape(hint)}</p></td>'
        for label, value, hint in cards
    )
    return f'<table class="kpis"><tr>{cells}</tr></table>'


def _overview(facts: WsrPlanFacts) -> str:
    text = None
    if facts.executive_summary and facts.executive_summary.summary.strip():
        text = facts.executive_summary.summary
    else:
        text = facts.executive_overview
    return f"<p>{_esc(text)}</p>"


def _timeline(facts: WsrPlanFacts) -> str:
    phases = [
        phase
        for phase in (facts.timeline or [])
        if (phase.planned_start or phase.planned_finish or phase.actual_start or phase.actual_finish)
    ]
    if not phases:
        return "<p>A timeline cannot be generated</p>"
    starts = [
        _day(phase.planned_start or phase.actual_start or phase.planned_finish or phase.actual_finish)
        for phase in phases
    ]
    ends = [
        _day(phase.planned_finish or phase.actual_finish or phase.planned_start or phase.actual_start)
        for phase in phases
    ]
    starts_ok = [item for item in starts if item]
    ends_ok = [item for item in ends if item]
    if not starts_ok or not ends_ok:
        return "<p>A timeline cannot be generated</p>"
    minimum = min(starts_ok)
    maximum = max(ends_ok)
    span = max((maximum - minimum).days, 1)
    rows = []
    for index, phase in enumerate(phases):
        start = (
            _day(phase.planned_start or phase.actual_start or phase.planned_finish or phase.actual_finish)
            or minimum
        )
        finish = (
            _day(phase.planned_finish or phase.actual_finish or phase.planned_start or phase.actual_start)
            or start
        )
        left = int(((start - minimum).days / span) * 100)
        width = max(int(((finish - start).days / span) * 100), 2)
        color = _GANTT_COLORS[index % len(_GANTT_COLORS)]
        planned_start = phase.planned_start or phase.actual_start
        planned_finish = phase.planned_finish or phase.actual_finish
        window = _window(planned_start, planned_finish, arrow=True)
        days = _duration_days(planned_start, planned_finish)
        dur = f"{days}d" if days is not None else "-"
        rows.append(
            f"<p><b>{html.escape(_wbs_label(phase, index + 1))}</b> {html.escape(phase.name)} "
            f"<span class='muted'>{html.escape(window)} {html.escape(dur)}</span></p>"
        )
        rows.append(_gantt_bar(phase.name, left, width, color))
    return "".join(rows)


def _phases(facts: WsrPlanFacts) -> str:
    phases = facts.phase_statuses or []
    if not phases:
        return "<p>Unavailable</p>"
    rows = [
        "<tr><td><b>WBS</b></td><td><b>Phase</b></td>"
        "<td><b>Planned End</b></td><td><b>Deviated Date</b></td>"
        "<td><b>Progress</b></td></tr>"
    ]
    for index, phase in enumerate(phases, start=1):
        if phase.progress is not None:
            progress = _percent(phase.progress)
        else:
            progress = _PHASE_STATE.get(phase.state, phase.state)
        planned = _short_date(phase.planned_finish)
        current = _short_date(phase.actual_finish)
        if planned == current:
            current = "-"
        rows.append(
            "<tr>"
            f"<td>{html.escape(_wbs_label(phase, index))}</td>"
            f"<td>{html.escape(phase.name)}</td>"
            f"<td>{html.escape(planned)}</td>"
            f"<td>{html.escape(current)}</td>"
            f"<td>{html.escape(progress)}</td>"
            "</tr>"
        )
    return f"<table>{''.join(rows)}</table>"


def _progress(facts: WsrPlanFacts) -> str:
    items = facts.progress_to_date or []
    if not items:
        return "<p>No tasks scheduled in the current week</p>"
    rows = [
        "<tr><td><b>Task</b></td><td><b>Start</b></td><td><b>End</b></td>"
        "<td><b>Complete</b></td></tr>"
    ]
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{html.escape(item.name)}</td>"
            f"<td>{html.escape(_short_date(item.scheduled_start))}</td>"
            f"<td>{html.escape(_short_date(item.scheduled_finish or item.date))}</td>"
            f"<td>{html.escape(_percent(item.progress))}</td>"
            "</tr>"
        )
    return f"<table>{''.join(rows)}</table>"


def _milestones(facts: WsrPlanFacts, as_of: str | None) -> str:
    items = facts.upcoming_milestones or []
    if not items:
        return "<p>No upcoming planned tasks</p>"
    as_of_d = _day(as_of)
    rows = [
        "<tr><td><b>Start</b></td><td><b>End</b></td>"
        "<td><b>Milestone / Activity</b></td><td></td></tr>"
    ]
    for item in items:
        item_day = _day(item.scheduled_start) or _day(item.date)
        today = ""
        if as_of_d and item_day and item_day == as_of_d:
            today = ' <span class="badge">Today</span>'
        start = html.escape(_week_date(item.scheduled_start))
        finish = html.escape(_week_date(item.scheduled_finish or item.date))
        name = html.escape(item.name)
        rows.append(
            f"<tr><td>{start}</td><td>{finish}</td><td>{name}</td><td>{today}</td></tr>"
        )
    return f"<table>{''.join(rows)}</table>"


def _insights(items: list[AiDerivedItem] | None) -> str:
    visible = [item for item in (items or []) if item.review_status != "removed"]
    if not visible:
        return "<p>No items identified from the plan</p>"
    return "".join(f"<p>{html.escape(item.content)}</p>" for item in visible)


def _gantt_bar(name: str, left: int, width: int, color: str) -> str:
    left = max(left, 0)
    width = max(min(width, 100 - left), 1)
    right = max(100 - left - width, 0)
    cells = []
    if left:
        cells.append(f'<td width="{left}%">&nbsp;</td>')
    cells.append(f'<td width="{width}%" bgcolor="{color}" class="gantt-bar">&nbsp;</td>')
    if right:
        cells.append(f'<td width="{right}%">&nbsp;</td>')
    return (
        '<table class="gantt" cellpadding="0" cellspacing="0">'
        f"<tr>{''.join(cells)}</tr></table>"
    )


def _section(number: int, title: str, inner: str) -> str:
    heading = html.escape(title)
    return (
        f'<div class="section card">'
        f'<p><span class="num">{number}</span> <b>{heading}</b></p>{inner}</div>'
    )


def _esc(value: object) -> str:
    if value in (None, "", []):
        return "Unavailable"
    return html.escape(str(value).replace("\u2014", "-").replace("\u2013", "-"))


def _wbs_label(phase, index: int) -> str:
    code = (getattr(phase, "wbs", None) or "").strip()
    return code or f"1.{index}"


def _percent(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value}%"


def _count(value: int | float | None, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)}{suffix}"
    return f"{value}{suffix}"


def _person_days(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"~{int(round(value)):,}"


def _window(start: str | None, finish: str | None, *, arrow: bool = False) -> str:
    start_d = _day(start)
    finish_d = _day(finish)
    if start_d is None and finish_d is None:
        return "Unavailable"
    if start_d is None:
        return _short_date(finish)
    if finish_d is None:
        return _short_date(start)
    left = f"{start_d.day} {start_d.strftime('%b')}"
    right = f"{finish_d.day} {finish_d.strftime('%b %Y')}"
    sep = " -> " if arrow else " - "
    return f"{left}{sep}{right}"


def _duration_days(start: str | None, finish: str | None) -> int | None:
    start_d = _day(start)
    finish_d = _day(finish)
    if start_d is None or finish_d is None:
        return None
    days = (finish_d - start_d).days + 1
    return days if days > 0 else 1


def _short_date(value: str | None) -> str:
    parsed = _day(value)
    if parsed is None:
        return "Unavailable"
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _compact_date(value: str | None) -> str:
    parsed = _day(value)
    if parsed is None:
        return "Unavailable"
    return f"{parsed.day} {parsed.strftime('%b')}"


def _week_date(value: str | None) -> str:
    parsed = _day(value)
    if parsed is None:
        return "Unavailable"
    return parsed.strftime("%d%b%Y")


def _day(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

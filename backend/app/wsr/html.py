from __future__ import annotations

import html
from datetime import date, datetime

from app.models import (
    AiDerivedItem,
    NamedDateValue,
    StatusReport,
    WsrPlanFacts,
)

_AI_SECTIONS = (
    ("client_needs", "What We Need From the Bank Team"),
    ("issues", "Issues"),
    ("dependencies", "Dependencies"),
    ("risks", "Risks & Focus Areas"),
    ("management_attention", "Management Attention"),
    ("decisions_required", "Decisions Required"),
    ("next_7_day_priorities", "Next Seven-Day Priorities"),
)
_GANTT_COLORS = ("#1f9d6a", "#3b82f6", "#4338ca", "#f59e0b", "#0ea5e9", "#8b5cf6", "#db2777")
_HEALTH = {
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
    "unavailable": "Unavailable - insufficient plan data",
}
_PHASE_STATE = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "complete": "Complete",
}


def render_wsr_html(handle: str, payload: StatusReport) -> str:
    facts = payload.facts or WsrPlanFacts()
    health = facts.project_health or payload.project_health or "unavailable"
    body = "".join(
        [
            _hero(payload, facts, health),
            _kpi_grid(facts),
            _section(1, "Executive Overview", _overview(facts)),
            _section(2, "Project Timeline", _timeline(facts)),
            _section(3, "Phase-Wise Status", _phases(facts)),
            _section(4, "Progress to Date", _progress(facts)),
            _section(5, "Upcoming Milestones", _milestones(facts, payload.as_of_date)),
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
body {{ font-family: Helvetica, Arial, sans-serif; color: #1e1b4b; font-size: 10px; }}
h1 {{ font-size: 18px; margin: 0 0 8px; color: #102033; }}
h2 {{ font-size: 13px; margin: 0; color: #102033; }}
h3 {{ font-size: 12px; margin: 0 0 6px; }}
p {{ margin: 0 0 6px; }}
.muted {{ color: #4a6278; }}
.card {{ border: 1px solid #d5e0ec; background: #ffffff; padding: 8px; }}
.hero td, .kpis td, .stats td {{
  border: 1px solid #d5e0ec; background: #f4f7fb; padding: 8px; vertical-align: top;
}}
.label {{ color: #4a6278; font-size: 8px; }}
.value {{ font-size: 14px; font-weight: bold; }}
.countdown {{ font-size: 28px; font-weight: bold; color: #b42318; }}
.ring {{ font-size: 22px; font-weight: bold; text-align: center; }}
.num {{ color: #ffffff; background: #4f46e5; padding: 2px 6px; }}
.health-on_track {{ color: #0b7a3e; font-weight: bold; }}
.health-at_risk {{ color: #9a6700; font-weight: bold; }}
.health-off_track {{ color: #b42318; font-weight: bold; }}
.health-unavailable {{ color: #4a6278; font-weight: bold; }}
.gantt {{ width: 100%; border-collapse: collapse; margin: 0 0 6px; }}
.gantt td {{ border: none; padding: 0; background: #ffffff; }}
.gantt-bar {{ height: 10px; }}
.badge {{ color: #b42318; font-weight: bold; }}
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


def _hero(payload: StatusReport, facts: WsrPlanFacts, health: str) -> str:
    countdown = (
        str(facts.countdown_days) if facts.countdown_days is not None else "Unavailable"
    )
    progress = _percent(facts.overall_progress)
    planned = " - planned data only" if payload.planned_only else ""
    owner = (
        f"Owner: {_esc(facts.project_owner)} - as of {_short_date(payload.as_of_date)}"
        f" - generated {_esc(payload.generated_at)}{html.escape(planned)}"
    )
    stamp = f"As of: {_esc(payload.as_of_date)} - Generated: {_esc(payload.generated_at)}"
    health_label = html.escape(_HEALTH.get(health, health))
    return f"""
<table class="hero">
<tr>
<td width="46%">
<h2>{_esc(facts.project_name)}</h2>
<p class="muted">{owner}</p>
<p class="muted">{stamp}</p>
<p class="health-{html.escape(health)}">Project health: {health_label}</p>
</td>
<td width="27%" align="center">
<p class="label">Countdown</p>
<p class="countdown">{html.escape(countdown)}</p>
<p class="muted">Days to Go-Live</p>
</td>
<td width="27%" align="center">
<p class="ring">{html.escape(progress if progress != "Unavailable" else "—")}</p>
<p class="muted">Overall Progress</p>
</td>
</tr>
</table>
"""


def _kpi_grid(facts: WsrPlanFacts) -> str:
    work = "Unavailable"
    if facts.completed_work_items is not None and facts.planned_work_items is not None:
        work = f"{facts.completed_work_items} / {facts.planned_work_items}"
    elif facts.completed_work_items is not None:
        work = str(facts.completed_work_items)
    signed = facts.last_signed_off_milestone
    gate = facts.next_gate
    capacity_hint = "Actual vs planned work" if facts.capacity_utilization is not None else ""
    cards = [
        ("Overall Progress", _percent(facts.overall_progress), "By work completed"),
        ("Last Signed-Off Milestone", _named(signed), signed.name if signed else ""),
        ("Work Items Completed", work, "actual / planned" if "/" in work else ""),
        ("Team Capacity", _percent(facts.capacity_utilization), capacity_hint),
        ("Next Gate", _named_compact(gate), gate.name if gate else ""),
        ("Go-Live", _short_date(facts.planned_go_live_date), "Production dates"),
    ]
    rows = []
    for start in (0, 3):
        cells = "".join(
            f'<td width="33%"><p class="label">{html.escape(label)}</p>'
            f'<p class="value">{html.escape(value)}</p>'
            f'<p class="muted">{html.escape(hint)}</p></td>'
            for label, value, hint in cards[start : start + 3]
        )
        rows.append(f"<tr>{cells}</tr>")
    return f'<table class="kpis">{"".join(rows)}</table>'


def _overview(facts: WsrPlanFacts) -> str:
    stats = [
        ("Overall Progress", _percent(facts.overall_progress)),
        ("Phases to Go-Live", _count(facts.phase_count)),
        ("People Planned", _count(facts.people_planned)),
        ("Resources Deployed", _count(facts.resources_deployed)),
        ("Days to Go-Live", _count(facts.countdown_days, suffix="d")),
    ]
    cells = "".join(
        (
            f'<td width="20%"><p class="value">{html.escape(value)}</p>'
            f'<p class="muted">{html.escape(label)}</p></td>'
        )
        for label, value in stats
    )
    overview = _esc(facts.executive_overview)
    return f'<p>{overview}</p><table class="stats"><tr>{cells}</tr></table>'


def _timeline(facts: WsrPlanFacts) -> str:
    phases = [
        phase
        for phase in (facts.timeline or [])
        if phase.planned_start or phase.planned_finish
    ]
    if not phases:
        return "<p>A timeline cannot be generated</p>"
    starts = [_day(phase.planned_start or phase.planned_finish) for phase in phases]
    ends = [_day(phase.planned_finish or phase.planned_start) for phase in phases]
    starts_ok = [item for item in starts if item]
    ends_ok = [item for item in ends if item]
    if not starts_ok or not ends_ok:
        return "<p>A timeline cannot be generated</p>"
    minimum = min(starts_ok)
    maximum = max(ends_ok)
    span = max((maximum - minimum).days, 1)
    rows = []
    for index, phase in enumerate(phases):
        start = _day(phase.planned_start or phase.planned_finish) or minimum
        finish = _day(phase.planned_finish or phase.planned_start) or start
        left = int(((start - minimum).days / span) * 100)
        width = max(int(((finish - start).days / span) * 100), 2)
        color = _GANTT_COLORS[index % len(_GANTT_COLORS)]
        rows.append(_gantt_bar(phase.name, left, width, color))
    return "".join(rows)


def _phases(facts: WsrPlanFacts) -> str:
    phases = facts.phase_statuses or []
    if not phases:
        return "<p>Unavailable</p>"
    rows = [
        "<tr><td><b>WBS</b></td><td><b>Phase</b></td>"
        "<td><b>Planned timing</b></td><td><b>Progress</b></td></tr>"
    ]
    for index, phase in enumerate(phases, start=1):
        if phase.progress is not None:
            progress = _percent(phase.progress)
        else:
            progress = _PHASE_STATE.get(phase.state, phase.state)
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(phase.name)}</td>"
            f"<td>{_esc(phase.planned_start)} - {_esc(phase.planned_finish)}</td>"
            f"<td>{html.escape(progress)}</td>"
            "</tr>"
        )
    return f"<table>{''.join(rows)}</table>"


def _progress(facts: WsrPlanFacts) -> str:
    items = facts.progress_to_date or []
    if not items:
        return "<p>Unavailable</p>"
    rows = []
    for item in items:
        extra = f" - {_percent(item.progress)}" if item.progress is not None else ""
        rows.append(
            f"<p><b>{html.escape(item.name)}</b><br/>"
            f"<span class='muted'>{_esc(item.date)}{html.escape(extra)}</span></p>"
        )
    return "".join(rows)


def _milestones(facts: WsrPlanFacts, as_of: str | None) -> str:
    items = facts.upcoming_milestones or []
    if not items:
        return "<p>No upcoming milestone was identified</p>"
    as_of_d = _day(as_of)
    rows = []
    for item in items:
        delayed = ""
        item_day = _day(item.date)
        if as_of_d and item_day and item_day < as_of_d:
            delayed = ' <span class="badge">DELAYED</span>'
        when = html.escape(_short_date(item.date))
        name = html.escape(item.name)
        rows.append(f"<p>{when} {name}{delayed}</p>")
    return "".join(rows)


def _insights(items: list[AiDerivedItem] | None) -> str:
    visible = [item for item in (items or []) if item.review_status != "removed"]
    if not visible:
        return "<p>No items identified from the plan</p>"
    return "".join(
        f"<p><b>AI-derived</b> {html.escape(item.content)}</p>" for item in visible
    )


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
        f"<p>{html.escape(name)}</p>"
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


def _percent(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value}%"


def _count(value: int | None, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    return f"{value}{suffix}"


def _named(value: NamedDateValue | None) -> str:
    if value is None or not value.name:
        return "Unavailable"
    if not value.date:
        return value.name
    return f"{value.name} ({_compact_date(value.date)})"


def _named_compact(value: NamedDateValue | None) -> str:
    if value is None:
        return "Unavailable"
    if value.date:
        return _compact_date(value.date)
    return value.name or "Unavailable"


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

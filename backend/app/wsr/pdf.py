from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import NamedDateValue, StatusReport, WsrPlanFacts

_SECTIONS = (
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

_NAVY = colors.HexColor("#102033")
_MUTED = colors.HexColor("#4a6278")
_LINE = colors.HexColor("#d5e0ec")
_BG = colors.HexColor("#f4f7fb")
_WHITE = colors.white
_HEALTH = {
    "on_track": colors.HexColor("#0b7a3e"),
    "at_risk": colors.HexColor("#9a6700"),
    "off_track": colors.HexColor("#b42318"),
    "unavailable": _MUTED,
}
_HEALTH_LABELS = {
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
    "unavailable": "Unavailable - insufficient plan data",
}
_EMPTY_AI = "No items identified from the plan"
_AI_KEYS = {
    "client_needs",
    "risks",
    "issues",
    "dependencies",
    "management_attention",
    "decisions_required",
    "next_7_day_priorities",
}
_PHASE_STATE = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "complete": "Complete",
}


def render_wsr_pdf(handle: str, payload: StatusReport) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="WSR & Insights",
        author="Project Automation",
    )
    styles = _styles()
    facts = payload.facts
    health = (facts.project_health if facts else payload.project_health) or "unavailable"
    story: list = [
        Paragraph("WSR &amp; Insights", styles["title"]),
        Spacer(1, 4 * mm),
        _identity_table(handle, payload, facts, health, styles),
        Spacer(1, 6 * mm),
        Paragraph("Project summary", styles["section"]),
        _metrics_table(_summary_metrics(facts), styles),
        Spacer(1, 6 * mm),
    ]
    for key, heading in _SECTIONS:
        blocks = [Paragraph(_xml(heading), styles["section"]), Spacer(1, 2 * mm)]
        blocks.extend(_section_flowables(key, payload, facts, styles))
        blocks.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(blocks))
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "WsrTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=_NAVY,
            spaceAfter=0,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "WsrSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=_NAVY,
            spaceBefore=0,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "WsrBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=_NAVY,
        ),
        "muted": ParagraphStyle(
            "WsrMuted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=_MUTED,
        ),
        "label": ParagraphStyle(
            "WsrLabel",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=_MUTED,
            leading=9,
        ),
        "value": ParagraphStyle(
            "WsrValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=_NAVY,
            leading=13,
        ),
        "health": ParagraphStyle(
            "WsrHealth",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
        ),
    }


def _identity_table(
    handle: str,
    payload: StatusReport,
    facts: WsrPlanFacts | None,
    health: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    health_style = ParagraphStyle(
        "WsrHealthValue",
        parent=styles["health"],
        textColor=_HEALTH.get(health, _MUTED),
    )
    identity = Table(
        [
            [
                Paragraph(_xml(facts.project_name if facts else None), styles["value"]),
                Paragraph(_xml(_HEALTH_LABELS.get(health, health)), health_style),
            ],
            [
                Paragraph(
                    _xml(f"Owner: {_display(facts.project_owner if facts else None)}"),
                    styles["muted"],
                ),
                Paragraph(
                    _xml(f"Project health: {_HEALTH_LABELS.get(health, health)}"), styles["muted"]
                ),
            ],
            [
                Paragraph(_xml(f"As of: {_display(payload.as_of_date)}"), styles["muted"]),
                Paragraph(_xml(f"Generated: {_display(payload.generated_at)}"), styles["muted"]),
            ],
            [
                Paragraph(_xml(f"Request: {handle}"), styles["muted"]),
                Paragraph(
                    _xml("Planned data only" if payload.planned_only else ""),
                    styles["muted"],
                ),
            ],
        ],
        colWidths=[105 * mm, 70 * mm],
    )
    identity.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BG),
                ("BOX", (0, 0), (-1, -1), 0.4, _LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return identity


def _summary_metrics(facts: WsrPlanFacts | None) -> list[tuple[str, str]]:
    return [
        ("Overall Progress", _percent(facts.overall_progress if facts else None)),
        ("Last Signed-Off Milestone", _named(facts.last_signed_off_milestone if facts else None)),
        ("Work Items Completed", _count(facts.completed_work_items if facts else None)),
        ("Team Capacity", _percent(facts.capacity_utilization if facts else None)),
        ("Next Gate", _named(facts.next_gate if facts else None)),
        ("Go-Live", _display(facts.planned_go_live_date if facts else None)),
    ]


def _overview_metrics(facts: WsrPlanFacts | None) -> list[tuple[str, str]]:
    return [
        ("Overall Progress", _percent(facts.overall_progress if facts else None)),
        ("Phases to Go-Live", _count(facts.phase_count if facts else None)),
        ("People Planned", _count(facts.people_planned if facts else None)),
        ("Resources Deployed", _count(facts.resources_deployed if facts else None)),
        ("Days to Go-Live", _count(facts.countdown_days if facts else None)),
    ]


def _metrics_table(
    rows: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    cells: list[list] = []
    pair: list = []
    for label, value in rows:
        pair.append(_metric_cell(label, value, styles))
        if len(pair) == 3:
            cells.append(pair)
            pair = []
    if pair:
        while len(pair) < 3:
            pair.append(Paragraph("", styles["body"]))
        cells.append(pair)
    table = Table(cells, colWidths=[58 * mm, 58 * mm, 59 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _WHITE),
                ("BOX", (0, 0), (-1, -1), 0.4, _LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, _LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _metric_cell(label: str, value: str, styles: dict[str, ParagraphStyle]) -> Table:
    inner = Table(
        [
            [Paragraph(_xml(label), styles["label"])],
            [Paragraph(_xml(value), styles["value"])],
        ]
    )
    inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return inner


def _section_flowables(
    key: str,
    payload: StatusReport,
    facts: WsrPlanFacts | None,
    styles: dict[str, ParagraphStyle],
) -> list:
    body = styles["body"]
    muted = styles["muted"]
    if key in _AI_KEYS:
        items = [item for item in getattr(payload, key) if item.review_status != "removed"]
        if not items:
            return [Paragraph(_xml(_EMPTY_AI), muted)]
        flow: list = []
        for item in items:
            flow.append(Paragraph(_xml(f"- {item.content}"), body))
        return flow
    if key == "executive_overview":
        blocks = [_metrics_table(_overview_metrics(facts), styles), Spacer(1, 3 * mm)]
        overview = facts.executive_overview if facts else None
        blocks.append(Paragraph(_xml(_display(overview)), body if overview else muted))
        return blocks
    if key == "timeline":
        timeline = facts.timeline if facts else None
        if not timeline:
            return [Paragraph(_xml("A timeline cannot be generated"), muted)]
        return [
            Paragraph(
                _xml(
                    f"- {phase.name}: {_display(phase.planned_start)} - "
                    f"{_display(phase.planned_finish)}"
                ),
                body,
            )
            for phase in timeline
        ]
    if key == "phase_statuses":
        phases = facts.phase_statuses if facts else []
        if not phases:
            return [Paragraph(_xml("Unavailable"), muted)]
        return [
            Paragraph(
                _xml(
                    f"- {phase.name}: {_PHASE_STATE.get(phase.state, phase.state)}"
                    f" ({_display(phase.planned_start)} - {_display(phase.planned_finish)})"
                ),
                body,
            )
            for phase in phases
        ]
    if key == "progress_to_date":
        items = facts.progress_to_date if facts else []
        if not items:
            return [Paragraph(_xml("Unavailable"), muted)]
        return [
            Paragraph(
                _xml(f"- {item.name}: {_display(item.date)} ({_percent(item.progress)})"),
                body,
            )
            for item in items
        ]
    if key == "upcoming_milestones":
        items = facts.upcoming_milestones if facts else []
        if not items:
            return [Paragraph(_xml("No upcoming milestone was identified"), muted)]
        return [Paragraph(_xml(f"- {item.name}: {_display(item.date)}"), body) for item in items]
    return [Paragraph(_xml("Unavailable"), muted)]


def _named(value: NamedDateValue | None) -> str:
    if value is None or not value.name:
        return "Unavailable"
    if not value.date:
        return value.name
    return f"{value.name} ({value.date})"


def _percent(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value}%"


def _count(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    return str(value)


def _display(value: object) -> str:
    if value in (None, "", []):
        return "Unavailable"
    return _plain(str(value))


def _plain(value: str) -> str:
    return value.replace("\u2014", "-").replace("\u2013", "-")


def _xml(value: object) -> str:
    text = _plain(str(value))
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(_LINE)
    canvas.setFillColor(_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.line(document.leftMargin, 12 * mm, document.pagesize[0] - document.rightMargin, 12 * mm)
    canvas.drawString(document.leftMargin, 8 * mm, "WSR & Insights")
    canvas.drawRightString(
        document.pagesize[0] - document.rightMargin,
        8 * mm,
        f"Page {document.page}",
    )
    canvas.restoreState()

"""Deterministic, document-grounded Scope of Work analysis.

Findings must quote or clearly match language in the uploaded text.
Missing-requirement flags are only raised when the document is substantial
and the expected clause is actually absent.
"""

from __future__ import annotations

import re
from typing import Any

from app.models import AnalysisReport, SowFinding

_CATEGORIES = (
    "gray_areas",
    "risks",
    "missing_requirements",
    "assumptions",
    "dependencies",
    "clarification_questions",
)

_VAGUE = (
    "reasonable",
    "reasonably",
    "timely",
    "as needed",
    "as required",
    "as appropriate",
    "as soon as possible",
    "asap",
    "promptly",
    "periodically",
    "from time to time",
    "tbd",
    "to be determined",
    "to be confirmed",
    "to be agreed",
    "best effort",
    "best endeavours",
    "adequate",
    "sufficient",
    "if required",
    "mutually agreed",
    "subject to discussion",
    "wherever possible",
    "including but not limited to",
    "not limited to",
)

_RISK_MARKERS = (
    "liquidated damage",
    "penalty",
    "penalties",
    "termination",
    "terminate",
    "indemnif",
    "liability",
    "breach",
    "non-compliance",
    "non compliance",
    "force majeure",
    "warranty",
    "warrantee",
    "delay penalty",
    "service credit",
)

_DEPENDENCY_MARKERS = (
    "depends on",
    "dependent on",
    "subject to",
    "provided that",
    "client shall",
    "bank shall",
    "customer shall",
    "ibl shall",
    "access to",
    "third party",
    "third-party",
    "provided by the client",
    "provided by the bank",
    "contingent on",
)

_ASSUMPTION_MARKERS = (
    "it is assumed",
    "assumption",
    "assumptions",
    "it is understood",
    "we assume",
    "vendor assumes",
)

_EXPECTED = (
    (
        "acceptance",
        ("acceptance criteria", "acceptance test", "uat", "user acceptance", "sign-off criteria"),
        "Acceptance criteria",
        "No measurable acceptance or UAT criteria are stated.",
        "Add dated, testable acceptance criteria and the sign-off owner.",
        "high",
    ),
    (
        "sla",
        ("sla", "service level", "uptime", "response time", "severity 1"),
        "Service levels",
        "No service-level or response-time targets are stated.",
        "Add SLAs (uptime, severity, response/restore) if operations are in scope.",
        "medium",
    ),
    (
        "out_of_scope",
        ("out of scope", "out-of-scope", "not in scope", "exclusions", "excluded from"),
        "Out of scope",
        "The document does not state what is out of scope.",
        "Add an explicit out-of-scope / exclusions list.",
        "medium",
    ),
    (
        "timeline",
        ("go-live", "go live", "timeline", "milestone", "delivery date", "completion date"),
        "Delivery timeline",
        "No Go-Live date, milestone, or delivery date is stated.",
        "Add a dated delivery / Go-Live milestone.",
        "high",
    ),
    (
        "change",
        ("change request", "change control", "variation", "change management"),
        "Change control",
        "No change-request or variation process is stated.",
        "Add how scope changes are requested, approved, and priced.",
        "medium",
    ),
    (
        "raci",
        ("raci", "roles and responsibilities", "responsible party", "accountable"),
        "Roles and responsibilities",
        "Ownership of deliverables is not defined (RACI or equivalent).",
        "Name who is responsible, accountable, consulted, and informed.",
        "low",
    ),
)


def analyze_scope_of_work(text: str) -> AnalysisReport:
    source = (text or "").strip()
    buckets: dict[str, list[SowFinding]] = {key: [] for key in _CATEGORIES}
    if not source:
        return AnalysisReport(summary="No extractable Scope of Work text was found.")

    sentences = _sentences(source)
    _collect_phrase_hits(buckets["gray_areas"], sentences, _VAGUE, "gray_areas", "Ambiguous language")
    _collect_phrase_hits(buckets["risks"], sentences, _RISK_MARKERS, "risks", "Stated commercial or delivery risk")
    _collect_phrase_hits(
        buckets["dependencies"],
        sentences,
        _DEPENDENCY_MARKERS,
        "dependencies",
        "External or client dependency",
    )
    _collect_phrase_hits(
        buckets["assumptions"],
        sentences,
        _ASSUMPTION_MARKERS,
        "assumptions",
        "Documented assumption",
    )
    if _looks_like_scope_document(source):
        _collect_missing(buckets["missing_requirements"], source)
    _collect_questions(buckets, source)

    for key in _CATEGORIES:
        buckets[key] = _dedupe(buckets[key])[:8]

    summary = _summary(source, buckets)
    return AnalysisReport(summary=summary, **buckets)


def ground_report(report: AnalysisReport, source: str) -> AnalysisReport:
    """Drop findings that are not supported by the uploaded text."""

    hay = _fold(source)
    sentences = _sentences(source)
    substantial = _looks_like_scope_document(source)
    kept: dict[str, list[SowFinding]] = {}
    for key in _CATEGORIES:
        rows: list[SowFinding] = []
        for item in getattr(report, key):
            grounded = _finding_in_source(item, hay, sentences, key, substantial)
            if grounded is None:
                continue
            rows.append(grounded)
        kept[key] = _dedupe(rows)[:8]
    summary = str(report.summary or "").strip()
    if summary and not _summary_supported(summary, hay):
        summary = _summary(source, kept)
    if not summary:
        summary = _summary(source, kept)
    return AnalysisReport(summary=summary, **kept)


def merge_scope_reports(primary: AnalysisReport, extra: AnalysisReport, source: str) -> AnalysisReport:
    grounded_extra = ground_report(extra, source)
    buckets: dict[str, list[SowFinding]] = {}
    for key in _CATEGORIES:
        combined = list(getattr(primary, key)) + list(getattr(grounded_extra, key))
        buckets[key] = _dedupe(combined)[:8]
    summary = str(extra.summary or "").strip()
    if not summary or not _summary_supported(summary, _fold(source)):
        summary = primary.summary
    return AnalysisReport(summary=summary, **buckets)


def _collect_phrase_hits(
    dest: list[SowFinding],
    sentences: list[str],
    markers: tuple[str, ...],
    category: str,
    title: str,
) -> None:
    seen: set[str] = set()
    for sentence in sentences:
        folded = _fold(sentence)
        for marker in markers:
            if marker not in folded:
                continue
            key = f"{marker}:{folded[:80]}"
            if key in seen:
                continue
            seen.add(key)
            dest.append(
                SowFinding(
                    category=category,
                    priority=_priority_for(category, marker),
                    title=title,
                    description=_clip(sentence),
                    recommendation=_recommendation(category, marker),
                    evidence=_clip(sentence, 220),
                )
            )
            break


def _collect_missing(dest: list[SowFinding], source: str) -> None:
    folded = _fold(source)
    for _code, needles, title, description, recommendation, priority in _EXPECTED:
        if _has_clause(folded, needles):
            continue
            continue
        dest.append(
            SowFinding(
                category="missing_requirements",
                priority=priority,  # type: ignore[arg-type]
                title=f"Missing: {title}",
                description=description,
                recommendation=recommendation,
                evidence="",
            )
        )


def _collect_questions(buckets: dict[str, list[SowFinding]], source: str) -> None:
    questions: list[SowFinding] = []
    for item in buckets["gray_areas"][:4]:
        questions.append(
            SowFinding(
                category="clarification_questions",
                priority=item.priority or "medium",
                title="Clarify ambiguous wording",
                description=f"What measurable meaning should replace: “{_clip(item.evidence or item.description, 140)}”?",
                recommendation="Record the agreed definition in the Scope of Work before delivery starts.",
                evidence=item.evidence,
            )
        )
    for item in buckets["missing_requirements"][:3]:
        questions.append(
            SowFinding(
                category="clarification_questions",
                priority=item.priority or "medium",
                title="Confirm a missing clause",
                description=item.description.replace("No ", "Please confirm ").replace(" are stated.", "."),
                recommendation=item.recommendation,
                evidence="",
            )
        )
    folded = _fold(source)
    if _looks_like_scope_document(source) and not any(
        token in folded for token in ("go-live", "go live", "delivery date", "completion date")
    ):
        questions.append(
            SowFinding(
                category="clarification_questions",
                priority="high",
                title="Confirm Go-Live date",
                description="What is the target Go-Live / delivery date for this scope?",
                recommendation="Add a dated Go-Live milestone owned by both parties.",
                evidence="",
            )
        )
    buckets["clarification_questions"] = questions


def _looks_like_scope_document(source: str) -> bool:
    if len(source) >= 400:
        return True
    headings = sum(
        1
        for token in ("scope", "deliverable", "timeline", "payment", "assumption", "dependenc")
        if token in _fold(source)
    )
    return headings >= 2


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 12][:400]


def _finding_in_source(
    item: SowFinding,
    hay: str,
    sentences: list[str],
    category: str,
    substantial: bool,
) -> SowFinding | None:
    quote = (item.evidence or item.description or "").strip()
    if category == "missing_requirements":
        return _ground_missing(item, hay, substantial)
    if category == "clarification_questions":
        return _ground_question(item, hay, substantial)
    evidence = ""
    if quote and _quote_in(quote, hay):
        evidence = item.evidence or _clip(quote, 220)
    elif quote:
        window = _distinctive_window(quote)
        if window and window in hay:
            evidence = item.evidence or _clip(quote, 220)
    if not evidence:
        matched = _supporting_sentence(item, sentences)
        if matched:
            evidence = _clip(matched, 220)
    if not evidence:
        return None
    return item.model_copy(update={"evidence": evidence, "category": category})


def _ground_missing(item: SowFinding, hay: str, substantial: bool) -> SowFinding | None:
    if not substantial:
        return None
    blob = _fold(f"{item.title} {item.description}")
    for _code, needles, title, _description, _recommendation, _priority in _EXPECTED:
        titled = title.casefold() in blob or _has_clause(blob, needles)
        if not titled:
            continue
        if _has_clause(hay, needles):
            return None
        return item
    return item


def _ground_question(item: SowFinding, hay: str, substantial: bool) -> SowFinding | None:
    evidence = (item.evidence or "").strip()
    if evidence:
        window = _distinctive_window(evidence)
        if _quote_in(evidence, hay) or (window and window in hay):
            return item
        return None
    blob = _fold(f"{item.title} {item.description}")
    if any(marker in blob and marker in hay for marker in _VAGUE + _RISK_MARKERS + _DEPENDENCY_MARKERS):
        return item
    if not substantial:
        return None
    for _code, needles, title, _description, _recommendation, _priority in _EXPECTED:
        if title.casefold() in blob or _has_clause(blob, needles):
            if _has_clause(hay, needles):
                return None
            return item
    if "go-live" in blob or "go live" in blob or "delivery date" in blob:
        if any(token in hay for token in ("go-live", "go live", "delivery date", "completion date")):
            return None
        return item
    return None


def _supporting_sentence(item: SowFinding, sentences: list[str]) -> str:
    blob = _fold(f"{item.title} {item.description} {item.evidence}")
    markers = _VAGUE + _RISK_MARKERS + _DEPENDENCY_MARKERS + _ASSUMPTION_MARKERS
    hits = [marker for marker in markers if marker in blob]
    if not hits:
        return ""
    for sentence in sentences:
        folded = _fold(sentence)
        if any(marker in folded for marker in hits):
            return sentence
    return ""


def _quote_in(quote: str, hay: str) -> bool:
    folded = _fold(quote)
    if len(folded) < 8:
        return False
    return folded in hay


def _distinctive_window(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.casefold())
    words = [w for w in words if len(w) > 2]
    if len(words) < 5:
        return " ".join(words)
    return " ".join(words[:8])


def _summary_supported(summary: str, hay: str) -> bool:
    words = [w for w in re.findall(r"[a-z]{4,}", summary.casefold())]
    if len(words) < 4:
        return False
    hits = sum(1 for word in words if word in hay)
    return hits / len(words) >= 0.5


def _summary(source: str, buckets: dict[str, list[Any]]) -> str:
    total = sum(len(buckets.get(key) or []) for key in _CATEGORIES)
    identity = _identity_line(source)
    if total == 0:
        if identity:
            return f"{identity} No gray areas, risks, gaps, assumptions, or dependencies were identified in the extracted text."
        return "No gray areas, risks, gaps, assumptions, or dependencies were identified in the extracted Scope of Work."
    lead = identity + " " if identity else ""
    return f"{lead}{total} findings grounded in the uploaded Scope of Work across six review categories."


def _identity_line(source: str) -> str:
    for line in source.splitlines():
        text = " ".join(line.split()).strip()
        if 12 <= len(text) <= 120 and not text.endswith(":"):
            lower = text.casefold()
            if any(token in lower for token in ("scope of work", "statement of work", "proposal", "project")):
                return text.rstrip(".") + "."
    return ""


def _priority_for(category: str, marker: str) -> str:
    if category == "risks":
        return "high"
    if marker in {"reasonable", "reasonably", "tbd", "to be determined"}:
        return "high"
    return "medium"


def _recommendation(category: str, marker: str) -> str:
    if category == "gray_areas":
        return f"Replace “{marker}” with a dated, measurable obligation in the Scope of Work."
    if category == "risks":
        return "Record owner, trigger, and mitigation for this clause before kickoff."
    if category == "dependencies":
        return "Name the provider, due date, and what happens if the dependency slips."
    if category == "assumptions":
        return "Confirm the assumption in writing or convert it into a stated requirement."
    return "Resolve this item in the signed Scope of Work."


def _dedupe(items: list[SowFinding]) -> list[SowFinding]:
    seen: set[str] = set()
    unique: list[SowFinding] = []
    for item in items:
        keys = [_fold(f"{item.title}:{item.description[:80]}")]
        evid = _fold(item.evidence or "")[:160]
        if evid:
            keys.append(f"e:{evid}")
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        unique.append(item)
    return unique


def _has_clause(hay: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        token = needle.strip()
        if not token:
            continue
        if " " in token or "-" in token or len(token) > 4:
            if token in hay:
                return True
            continue
        if re.search(rf"\b{re.escape(token)}\b", hay):
            return True
    return False


def _fold(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _clip(text: str, limit: int = 280) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"

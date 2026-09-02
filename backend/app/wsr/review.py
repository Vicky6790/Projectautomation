from __future__ import annotations

from app import storage as storage_mod
from app.errors import AppError
from app.models import (
    AiDerivedItem,
    ProcessingResponse,
    StatusReport,
    WsrEvidenceResponse,
    WsrItemDecision,
)
from app.wsr.evidence import AI_SECTIONS, STORED_AI_SECTIONS, items_exportable


def iter_items(report: StatusReport) -> list[AiDerivedItem]:
    items: list[AiDerivedItem] = []
    for key in STORED_AI_SECTIONS:
        items.extend(getattr(report, key))
    for board in report.projects:
        for key in STORED_AI_SECTIONS:
            items.extend(getattr(board, key))
    return items


def find_item(report: StatusReport, item_id: str) -> AiDerivedItem | None:
    for item in iter_items(report):
        if item.id == item_id:
            return item
    return None


def find_items(report: StatusReport, item_id: str) -> list[AiDerivedItem]:
    return [item for item in iter_items(report) if item.id == item_id]


def _loaded_report(handle: str) -> tuple[ProcessingResponse, StatusReport]:
    job = storage_mod.store.get_job(handle)
    if job.module != "wsr":
        raise AppError(404, "ITEM_NOT_FOUND", "No WSR insight exists for this request")
    if job.status != "succeeded" or not job.result:
        raise AppError(
            409,
            "REVIEW_NOT_ALLOWED",
            "Insights can be reviewed only after WSR generation has completed",
        )
    return job, StatusReport.model_validate(job.result)


def review_item(handle: str, item_id: str, body: WsrItemDecision) -> ProcessingResponse:
    _job, report = _loaded_report(handle)
    items = find_items(report, item_id)
    if not items:
        raise AppError(404, "ITEM_NOT_FOUND", "No WSR insight exists for this request")
    as_of = report.as_of_date
    generated_at = report.generated_at
    if body.decision == "edited":
        text = (body.content or "").strip()
        if not text:
            raise AppError(
                400,
                "INVALID_REVIEW",
                "An edited insight must include replacement content",
            )
        for item in items:
            item.content = text
            item.review_status = "edited"
    else:
        for item in items:
            item.review_status = body.decision
    report.exportable = items_exportable(*_ai_section_values(report))
    report.as_of_date = as_of
    report.generated_at = generated_at
    return storage_mod.store.set_status(
        handle,
        "succeeded",
        result=report.model_dump(mode="json"),
    )


def item_evidence(handle: str, item_id: str) -> WsrEvidenceResponse:
    _job, report = _loaded_report(handle)
    item = find_item(report, item_id)
    if item is None:
        raise AppError(404, "ITEM_NOT_FOUND", "No WSR insight exists for this request")
    return WsrEvidenceResponse(
        item_id=item.id,
        content=item.content,
        section=item.section,
        review_status=item.review_status,
        evidence_references=item.evidence_references,
    )


def _ai_section_values(report: StatusReport) -> list[list[AiDerivedItem]]:
    rows = [getattr(report, key) for key in AI_SECTIONS]
    for board in report.projects:
        rows.extend(getattr(board, key) for key in AI_SECTIONS)
    return rows

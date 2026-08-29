from __future__ import annotations

from io import BytesIO

from xhtml2pdf import pisa

from app.errors import AppError
from app.models import StatusReport
from app.wsr.html import render_delay_mapping_html, render_wsr_html


def render_wsr_pdf(handle: str, payload: StatusReport) -> bytes:
    return _pdf_from_html(render_wsr_html(handle, payload))


def render_delay_mapping_pdf(handle: str, payload: StatusReport) -> bytes:
    return _pdf_from_html(render_delay_mapping_html(handle, payload))


def _pdf_from_html(html: str) -> bytes:
    output = BytesIO()
    try:
        result = pisa.CreatePDF(html, dest=output, encoding="utf-8")
    except (ValueError, TypeError, AttributeError) as exc:
        raise AppError(500, "WSR_PDF_FAILED", "The WSR PDF could not be rendered") from exc
    if result.err:
        raise AppError(500, "WSR_PDF_FAILED", "The WSR PDF could not be rendered")
    body = output.getvalue()
    if not body.startswith(b"%PDF"):
        raise AppError(500, "WSR_PDF_FAILED", "The WSR PDF could not be rendered")
    return body

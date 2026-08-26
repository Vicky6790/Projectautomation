from __future__ import annotations

from io import BytesIO

from xhtml2pdf import pisa

from app.errors import AppError
from app.models import StatusReport
from app.wsr.html import render_wsr_html


def render_wsr_pdf(handle: str, payload: StatusReport) -> bytes:
    html = render_wsr_html(handle, payload)
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

from io import BytesIO

from docx import Document


def docx_bytes(text: str = "This is a statement of work for the engagement.") -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def pdf_bytes(text: str = "This is a statement of work for the engagement.") -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    # Blank pages have no extractable text; callers that need text should use docx_bytes.
    _ = text
    return buffer.getvalue()

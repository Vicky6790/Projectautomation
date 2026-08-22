from fastapi.testclient import TestClient

from tests.helpers import docx_bytes, pdf_bytes


def test_rejects_unsupported_sow_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={"file": ("notes.txt", b"not a sow", "text/plain")},
        data={"module": "sow"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "PDF" in error["message"]
    assert "docx" in error["message"]


def test_rejects_empty_text_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={"file": ("scan.pdf", pdf_bytes("   "), "application/pdf")},
        data={"module": "sow"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_EXTRACTABLE_TEXT"


def test_extracts_docx_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={
            "file": (
                "sow.docx",
                docx_bytes("Deliverables include design and implementation work."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"module": "sow"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["extracted_text_available"] is True
    text = client.get(f"/api/v1/files/{body['id']}/text")
    assert text.status_code == 200
    assert "Deliverables" in text.json()["text"]


def test_wsr_rejects_unreadable_mpp(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={
            "file": ("plan.mpp", b"fake-mpp-bytes-for-type-check", "application/vnd.ms-project")
        },
        data={"module": "wsr"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNREADABLE_MPP"


def test_wsr_rejects_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={"file": ("sow.pdf", pdf_bytes(), "application/pdf")},
        data={"module": "wsr"},
    )
    assert response.status_code == 400
    assert ".mpp" in response.json()["error"]["message"]

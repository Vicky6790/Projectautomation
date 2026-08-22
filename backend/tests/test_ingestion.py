from fastapi.testclient import TestClient

from app.ingestion.policy import MPP_POLICY, SOW_POLICY
from app.ingestion.validator import format_size_limit
from tests.helpers import docx_bytes, pdf_bytes


def test_policy_limits_match_wo24() -> None:
    assert SOW_POLICY.extensions == frozenset({".pdf", ".docx"})
    assert SOW_POLICY.max_bytes == 25 * 1024 * 1024
    assert MPP_POLICY.extensions == frozenset({".mpp"})
    assert MPP_POLICY.max_bytes == 50 * 1024 * 1024
    assert format_size_limit(SOW_POLICY.max_bytes) == "25 MB"
    assert format_size_limit(MPP_POLICY.max_bytes) == "50 MB"


def test_rejects_unsupported_sow_type_on_module_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sow/uploads",
        files={"file": ("notes.txt", b"not a sow", "text/plain")},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "PDF" in error["message"]
    assert "docx" in error["message"]


def test_rejects_empty_sow_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sow/uploads",
        files={"file": ("sow.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_rejects_empty_text_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sow/uploads",
        files={"file": ("scan.pdf", pdf_bytes("   "), "application/pdf")},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "NO_EXTRACTABLE_TEXT"
    assert "text-based" in error["message"]


def test_extracts_pdf_text_on_sow_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sow/uploads",
        files={
            "file": (
                "sow.pdf",
                pdf_bytes("Deliverables include design and implementation work."),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["extracted_text_available"] is True
    text = client.get(f"/api/v1/files/{body['id']}/text")
    assert text.status_code == 200
    assert "Deliverables" in text.json()["text"]


def test_extracts_docx_tables(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sow/uploads",
        files={
            "file": (
                "sow.docx",
                docx_bytes(
                    "Statement of work.",
                    table_rows=[["Deliverable", "Due"], ["Portal", "Week 8"]],
                ),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    text = client.get(f"/api/v1/files/{response.json()['id']}/text")
    assert text.status_code == 200
    body = text.json()["text"]
    assert "Portal" in body
    assert "Week 8" in body


def test_sow_size_rejection_states_limit(client: TestClient, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 100)
    response = client.post(
        "/api/v1/sow/uploads",
        files={"file": ("sow.docx", b"x" * 101, "application/octet-stream")},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "FILE_TOO_LARGE"
    assert "100 bytes" in error["message"]


def test_plan_module_does_not_accept_uploads(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files",
        files={"file": ("sow.docx", docx_bytes(), "application/octet-stream")},
        data={"module": "plan"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_NOT_APPLICABLE"


def test_wsr_rejects_pdf_on_module_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wsr/uploads",
        files={"file": ("sow.pdf", pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_FILE_TYPE"
    assert ".mpp" in error["message"]


def test_wsr_rejects_non_project_bytes_named_mpp(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wsr/uploads",
        files={
            "file": ("plan.mpp", b"fake-mpp-bytes-for-type-check", "application/vnd.ms-project")
        },
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_FILE_TYPE"
    assert ".mpp" in error["message"]

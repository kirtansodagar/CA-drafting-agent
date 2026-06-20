"""Tests for protected backend agent endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import MAX_UPLOAD_BYTES
from app.main import app

client = TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


def test_web_frontend_is_served() -> None:
    """The professional browser frontend is served by FastAPI."""
    response = client.get("/")

    assert response.status_code == 200
    assert "CA Drafting Agent" in response.text


def test_agent_endpoint_rejects_missing_api_key(monkeypatch) -> None:
    """State-changing endpoints require the shared API key."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")

    response = client.post(
        "/agent/message",
        data={"session_id": "s1", "message": "Hello"},
    )

    assert response.status_code == 401


def test_agent_endpoint_rejects_invalid_api_key(monkeypatch) -> None:
    """Wrong API keys do not reach agent logic."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")

    response = client.post(
        "/agent/message",
        data={"session_id": "s1", "message": "Hello"},
        headers={"X-API-Key": "wrong"},
    )

    assert response.status_code == 401


def test_agent_upload_requires_consent(monkeypatch) -> None:
    """Document upload requires explicit Groq data-sharing consent."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")

    response = client.post(
        "/agent/message",
        data={"session_id": "s1", "client_name": "Mr. Sharma", "consent": "false"},
        files={"file": ("sample.pdf", b"%PDF-1.4\nsample", "application/pdf")},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert "Consent is required" in response.text


def test_agent_upload_rejects_fake_pdf(monkeypatch) -> None:
    """A .pdf extension is not enough without a PDF file header."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")

    response = client.post(
        "/agent/message",
        data={"session_id": "s1", "client_name": "Mr. Sharma", "consent": "true"},
        files={"file": ("sample.pdf", b"not a pdf", "application/pdf")},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert "valid PDF" in response.text


def test_agent_upload_rejects_oversized_pdf(monkeypatch) -> None:
    """PDF uploads are capped at the configured 25 MB limit."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")
    oversized_pdf = b"%PDF" + (b"0" * MAX_UPLOAD_BYTES)

    response = client.post(
        "/agent/message",
        data={"session_id": "s1", "client_name": "Mr. Sharma", "consent": "true"},
        files={"file": ("large.pdf", oversized_pdf, "application/pdf")},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert "25 MB" in response.text


def test_agent_upload_success_returns_draft_and_checklist(monkeypatch) -> None:
    """Valid uploads invoke parsing and the agent session."""
    monkeypatch.setenv("APP_API_KEY", "test-api-key")

    with (
        patch(
            "app.main.parse_document",
            return_value={
                "doc_type": "form_26as",
                "text": "Form 26AS Annual Tax Statement from TRACES",
                "char_count": 42,
                "file_name": "sample.pdf",
            },
        ),
        patch(
            "app.main.start_document_session",
            return_value={
                "assistant_message": "Draft ready.",
                "draft": "Dear Client",
                "checklist": "- Verify TDS",
                "doc_type": "form_26as",
                "client_name": "Mr. Sharma",
            },
        ),
    ):
        response = client.post(
            "/agent/message",
            data={
                "session_id": "s1",
                "client_name": "Mr. Sharma",
                "consent": "true",
            },
            files={"file": ("sample.pdf", b"%PDF-1.4\nsample", "application/pdf")},
            headers=_headers(),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"] == "Dear Client"
    assert payload["checklist"] == "- Verify TDS"
    assert payload["review_required"] is True

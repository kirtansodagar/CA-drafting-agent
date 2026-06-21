"""Tests for protected backend agent endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent import SESSION_STORE
from app.config import MAX_UPLOAD_BYTES
from app.main import app
from app.storage import get_case_by_session

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
    assert payload["case_id"]
    assert payload["draft"] == "Dear Client"
    assert payload["checklist"] == "- Verify TDS"
    assert payload["review_required"] is True


def test_cases_endpoint_lists_persisted_cases(monkeypatch) -> None:
    """Saved cases can be listed and loaded after generation."""
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
        upload_response = client.post(
            "/agent/message",
            data={
                "session_id": "persisted-list-session",
                "client_name": "Mr. Sharma",
                "consent": "true",
            },
            files={"file": ("sample.pdf", b"%PDF-1.4\nsample", "application/pdf")},
            headers=_headers(),
        )

    case_id = upload_response.json()["case_id"]
    list_response = client.get("/cases", headers=_headers())
    detail_response = client.get(f"/cases/{case_id}", headers=_headers())

    assert list_response.status_code == 200
    assert any(case["id"] == case_id for case in list_response.json()["cases"])
    assert detail_response.status_code == 200
    assert detail_response.json()["case"]["messages"][0]["content"] == "Draft ready."


def test_revision_restores_persisted_session_after_memory_clear(monkeypatch) -> None:
    """A saved case can be revised after in-memory agent state is lost."""
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
        upload_response = client.post(
            "/agent/message",
            data={
                "session_id": "persisted-revision-session",
                "client_name": "Mr. Sharma",
                "consent": "true",
            },
            files={"file": ("sample.pdf", b"%PDF-1.4\nsample", "application/pdf")},
            headers=_headers(),
        )

    assert upload_response.status_code == 200
    saved_case = get_case_by_session("persisted-revision-session")
    assert saved_case is not None
    SESSION_STORE.pop("persisted-revision-session", None)

    with patch(
        "app.agent.revise_draft",
        return_value={
            "draft": "Revised persisted draft",
            "doc_type": "form_26as",
            "client_name": "Mr. Sharma",
        },
    ):
        response = client.post(
            "/agent/message",
            data={
                "session_id": "persisted-revision-session",
                "message": "Make it shorter.",
            },
            headers=_headers(),
        )

    assert response.status_code == 200
    assert response.json()["draft"] == "Revised persisted draft"

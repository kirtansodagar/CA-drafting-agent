"""Tests for the LangGraph CA drafting agent flow."""

from unittest.mock import patch

from app.agent import SESSION_STORE, continue_document_session, start_document_session


def test_agent_flow_generates_draft_and_checklist() -> None:
    """Start a document session and store draft plus checklist state."""
    SESSION_STORE.clear()

    with (
        patch(
            "app.agent.generate_draft",
            return_value={
                "draft": "Dear Client,\n\nDraft for CA review.",
                "doc_type": "form_26as",
                "client_name": "Mr. Sharma",
            },
        ) as mock_draft,
        patch(
            "app.agent.generate_checklist",
            return_value={"checklist": "- Items to Verify\n- TDS amount"},
        ) as mock_checklist,
    ):
        result = start_document_session(
            "session-1",
            "Mr. Sharma",
            "form_26as",
            "Form 26AS Annual Tax Statement from TRACES",
        )

    assert result["draft"] == "Dear Client,\n\nDraft for CA review."
    assert result["checklist"] == "- Items to Verify\n- TDS amount"
    assert result["current_draft"] == result["draft"]
    assert SESSION_STORE["session-1"]["draft"] == result["draft"]
    mock_draft.assert_called_once()
    mock_checklist.assert_called_once()


def test_agent_flow_revises_existing_draft() -> None:
    """Continue a document session and replace the current draft."""
    SESSION_STORE.clear()
    SESSION_STORE["session-2"] = {
        "session_id": "session-2",
        "client_name": "Mr. Sharma",
        "doc_type": "form_26as",
        "extracted_text": "Form 26AS Annual Tax Statement from TRACES",
        "current_draft": "Original draft",
        "draft": "Original draft",
        "checklist": "- Verify TDS",
    }

    with patch(
        "app.agent.revise_draft",
        return_value={
            "draft": "Revised draft",
            "doc_type": "form_26as",
            "client_name": "Mr. Sharma",
        },
    ) as mock_revise:
        result = continue_document_session("session-2", "Make it shorter.")

    assert result["draft"] == "Revised draft"
    assert result["current_draft"] == "Revised draft"
    assert result["checklist"] == "- Verify TDS"
    mock_revise.assert_called_once()

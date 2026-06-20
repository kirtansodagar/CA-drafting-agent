"""Tests for Groq draft generation helpers."""

from unittest.mock import MagicMock, patch

from app.generator import generate_draft


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("app.generator.Groq")
def test_generate_draft_returns_expected_payload(mock_groq_class: MagicMock) -> None:
    """Return draft metadata when the Groq SDK call succeeds."""
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 25

    message = MagicMock()
    message.content = "Dear Client,\n\nThis is your draft letter."

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage

    client = MagicMock()
    client.chat.completions.create.return_value = response
    mock_groq_class.return_value = client

    result = generate_draft(
        "form_26as",
        "Form 26AS Annual Tax Statement from TRACES with relevant TDS details.",
        "Mr. Sharma",
    )

    assert result == {
        "draft": "Dear Client,\n\nThis is your draft letter.",
        "doc_type": "form_26as",
        "client_name": "Mr. Sharma",
    }
    mock_groq_class.assert_called_once_with(api_key="test-key")
    client.chat.completions.create.assert_called_once()


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("app.generator.Groq")
def test_generate_draft_returns_error_on_api_failure(
    mock_groq_class: MagicMock,
) -> None:
    """Return an error payload when the Groq SDK raises an exception."""
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("API unavailable")
    mock_groq_class.return_value = client

    result = generate_draft(
        "form_26as",
        "Form 26AS Annual Tax Statement from TRACES with relevant TDS details.",
        "Mr. Sharma",
    )

    assert result == {"error": "API unavailable"}


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("app.generator.Groq")
def test_generate_draft_returns_clean_quota_error(
    mock_groq_class: MagicMock,
) -> None:
    """Return a concise error payload when Groq quota or rate limit is reached."""
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError(
        "429 rate_limit_exceeded: quota exceeded"
    )
    mock_groq_class.return_value = client

    result = generate_draft(
        "form_26as",
        "Form 26AS Annual Tax Statement from TRACES with relevant TDS details.",
        "Mr. Sharma",
    )

    assert result == {
        "error": (
            "Groq quota or rate limit was reached for this API key. "
            "Check the Groq console limits for llama-3.3-70b-versatile, "
            "wait for the limit window to reset, or use a Groq API key/project "
            "with available capacity."
        )
    }


@patch.dict("os.environ", {}, clear=True)
@patch("app.generator.load_dotenv")
def test_generate_draft_requires_api_key(mock_load_dotenv: MagicMock) -> None:
    """Return an error payload when the Groq API key is missing."""
    result = generate_draft(
        "form_26as",
        "Form 26AS Annual Tax Statement from TRACES with relevant TDS details.",
        "Mr. Sharma",
    )

    assert result == {"error": "GROQ_API_KEY is not set."}
    mock_load_dotenv.assert_called_once()

"""Groq API integration for generating client-facing CA draft letters."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from groq import Groq

from app.prompts import (
    get_checklist_prompt,
    get_prompt_for_doc_type,
    get_revision_prompt,
    get_system_prompt,
)

MODEL_NAME = "llama-3.3-70b-versatile"


def _log_usage_metadata(response: object) -> None:
    """Log Groq token usage metadata when the API response provides it."""
    usage_metadata = getattr(response, "usage", None)
    prompt_tokens = getattr(usage_metadata, "prompt_tokens", "unknown")
    completion_tokens = getattr(usage_metadata, "completion_tokens", "unknown")
    print(
        "Groq token usage - "
        f"prompt: {prompt_tokens}, completion: {completion_tokens}"
    )


def _format_api_error(exc: Exception) -> str:
    """Return a concise, client-safe message for Groq API failures."""
    error_text = str(exc)
    normalized_error = error_text.lower()

    if (
        "429" in error_text
        or "quota" in normalized_error
        or "rate limit" in normalized_error
        or "rate_limit" in normalized_error
    ):
        return (
            "Groq quota or rate limit was reached for this API key. "
            "Check the Groq console limits for "
            f"{MODEL_NAME}, wait for the limit window to reset, or use a "
            "Groq API key/project with available capacity."
        )

    return error_text


def generate_draft(
    doc_type: str, extracted_text: str, client_name: str
) -> dict[str, str]:
    """Generate a professional client letter using Groq for the parsed document."""
    try:
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return {"error": "GROQ_API_KEY is not set."}

        system_prompt = get_system_prompt()
        user_prompt = get_prompt_for_doc_type(doc_type, extracted_text, client_name)

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        _log_usage_metadata(response)

        draft = response.choices[0].message.content.strip()

        if not draft:
            return {"error": "Groq returned an empty draft."}

        return {
            "draft": draft,
            "doc_type": doc_type,
            "client_name": client_name,
        }
    except Exception as exc:
        return {"error": _format_api_error(exc)}


def _generate_text(user_prompt: str, max_tokens: int = 1024) -> dict[str, str]:
    """Generate text from Groq with the shared system prompt."""
    try:
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return {"error": "GROQ_API_KEY is not set."}

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
        )

        _log_usage_metadata(response)

        content = response.choices[0].message.content.strip()
        if not content:
            return {"error": "Groq returned an empty response."}

        return {"content": content}
    except Exception as exc:
        return {"error": _format_api_error(exc)}


def generate_checklist(
    doc_type: str, extracted_text: str, client_name: str
) -> dict[str, str]:
    """Generate a CA review checklist for the parsed document."""
    generated = _generate_text(
        get_checklist_prompt(doc_type, extracted_text, client_name),
        max_tokens=700,
    )
    if "error" in generated:
        return {"error": generated["error"]}

    return {
        "checklist": generated["content"],
        "doc_type": doc_type,
        "client_name": client_name,
    }


def revise_draft(
    doc_type: str,
    extracted_text: str,
    client_name: str,
    current_draft: str,
    user_message: str,
) -> dict[str, str]:
    """Revise an existing draft using CA feedback and source document context."""
    generated = _generate_text(
        get_revision_prompt(
            doc_type,
            extracted_text,
            client_name,
            current_draft,
            user_message,
        ),
        max_tokens=1200,
    )
    if "error" in generated:
        return {"error": generated["error"]}

    return {
        "draft": generated["content"],
        "doc_type": doc_type,
        "client_name": client_name,
    }

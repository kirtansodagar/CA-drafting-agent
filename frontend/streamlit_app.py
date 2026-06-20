"""Streamlit chat workbench for the CA Drafting Agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
import requests
import streamlit as st

DEFAULT_AGENT_URL = "http://localhost:8000/agent/message"

load_dotenv()


def get_secret_or_env(name: str, default: str = "") -> str:
    """Read a setting from Streamlit secrets first, then environment."""
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value or os.getenv(name, default))


def get_agent_url() -> str:
    """Return the configured backend agent endpoint URL."""
    return get_secret_or_env("API_AGENT_URL", DEFAULT_AGENT_URL)


def get_api_key() -> str:
    """Return the shared backend API key."""
    return get_secret_or_env("APP_API_KEY")


def api_headers() -> dict[str, str]:
    """Build headers for backend requests."""
    api_key = get_api_key()
    return {"X-API-Key": api_key} if api_key else {}


def doc_type_badge(doc_type: str) -> str:
    """Return an HTML badge for a detected document type."""
    badge_config = {
        "form_26as": ("Form 26AS", "#1f8f4d"),
        "tax_notice": ("Income Tax Notice", "#b45309"),
        "itr_summary": ("ITR Summary", "#1f6feb"),
    }
    label, color = badge_config.get(doc_type, ("Unknown", "#6b7280"))
    return (
        f"<span style='background:{color}; color:white; padding:0.25rem 0.6rem; "
        "border-radius:0.4rem; font-size:0.85rem; font-weight:600;'>"
        f"{label}</span>"
    )


def submit_agent_upload(
    uploaded_file: object,
    client_name: str,
    session_id: str,
) -> requests.Response:
    """Send an uploaded PDF to the backend agent."""
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            "application/pdf",
        )
    }
    data = {
        "client_name": client_name,
        "session_id": session_id,
        "message": "Please analyze this document and prepare a draft.",
        "consent": "true",
    }
    return requests.post(
        get_agent_url(),
        files=files,
        data=data,
        headers=api_headers(),
        timeout=90,
    )


def submit_agent_message(session_id: str, message: str) -> requests.Response:
    """Send a follow-up instruction to the backend agent."""
    data = {"session_id": session_id, "message": message}
    return requests.post(
        get_agent_url(),
        data=data,
        headers=api_headers(),
        timeout=90,
    )


def extract_error_message(response: requests.Response) -> str:
    """Extract a readable error message from an unsuccessful API response."""
    try:
        payload = response.json()
        detail = payload.get("detail", "Unable to generate draft.")
        return str(detail)
    except Exception:
        return response.text or "Unable to generate draft."


def ensure_session_state() -> None:
    """Initialize Streamlit session keys used by the chat workbench."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_payload" not in st.session_state:
        st.session_state.agent_payload = {}


def main() -> None:
    """Render the chat workbench for uploading documents and revising drafts."""
    st.set_page_config(page_title="CA Drafting Agent", page_icon="CA", layout="wide")
    ensure_session_state()

    with st.sidebar:
        st.header("Case Setup")
        client_name = st.text_input("Client Name")
        uploaded_file = st.file_uploader("Upload Tax PDF", type=["pdf"])
        consent = st.checkbox(
            "I understand extracted tax document text will be sent to Groq to generate this draft."
        )

        if st.button("Start Agent Review", type="primary"):
            if not client_name.strip():
                st.error("Client name is required.")
            elif uploaded_file is None:
                st.error("Upload a PDF to start.")
            elif not consent:
                st.error("Consent is required before generation.")
            elif not get_api_key():
                st.error("APP_API_KEY is not configured in Streamlit secrets or env.")
            else:
                with st.spinner("Analyzing document and drafting..."):
                    try:
                        response = submit_agent_upload(
                            uploaded_file,
                            client_name.strip(),
                            st.session_state.session_id,
                        )
                    except requests.RequestException as exc:
                        st.error(f"Could not connect to backend: {exc}")
                        return

                if response.ok:
                    payload = response.json()
                    st.session_state.agent_payload = payload
                    st.session_state.messages = [
                        {
                            "role": "assistant",
                            "content": payload.get("assistant_message", ""),
                        }
                    ]
                else:
                    st.error(extract_error_message(response))

        st.caption("All output is draft material for CA review.")

    st.title("CA Drafting Agent")
    st.caption(
        "Drafting assistant for CA review. Verify facts before sharing anything with a client."
    )

    payload = st.session_state.agent_payload
    if not payload:
        st.info("Enter a client name, upload a tax PDF, and start the agent review.")
        return

    top_left, top_right = st.columns([1, 3])
    with top_left:
        st.markdown(
            doc_type_badge(payload.get("doc_type", "unknown")),
            unsafe_allow_html=True,
        )
        st.metric("Source Characters", payload.get("char_count", 0))
    with top_right:
        st.warning("Draft for CA review only. This is not final tax advice.")

    draft_tab, checklist_tab, chat_tab = st.tabs(
        ["Draft", "Verification Checklist", "Agent Chat"]
    )
    with draft_tab:
        st.text_area(
            "Generated Draft",
            value=payload.get("draft", ""),
            height=460,
        )
    with checklist_tab:
        st.text_area(
            "Checklist",
            value=payload.get("checklist", ""),
            height=460,
        )
    with chat_tab:
        for chat_message in st.session_state.messages:
            if chat_message.get("content"):
                with st.chat_message(chat_message["role"]):
                    st.write(chat_message["content"])

        user_message = st.chat_input("Ask for a revision or clarification")
        if user_message:
            st.session_state.messages.append({"role": "user", "content": user_message})
            with st.spinner("Revising draft..."):
                try:
                    response = submit_agent_message(
                        st.session_state.session_id,
                        user_message,
                    )
                except requests.RequestException as exc:
                    st.error(f"Could not connect to backend: {exc}")
                    return

            if response.ok:
                updated_payload = response.json()
                st.session_state.agent_payload = updated_payload
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": updated_payload.get("assistant_message", ""),
                    }
                )
                st.rerun()
            else:
                st.error(extract_error_message(response))


if __name__ == "__main__":
    main()

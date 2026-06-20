"""LangGraph orchestration for the CA drafting assistant."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.generator import generate_checklist, generate_draft, revise_draft


class AgentState(TypedDict, total=False):
    """Mutable state passed through the CA drafting graph."""

    mode: Literal["draft", "revise"]
    session_id: str
    client_name: str
    doc_type: str
    extracted_text: str
    user_message: str
    current_draft: str
    draft: str
    checklist: str
    assistant_message: str
    error: str


SESSION_STORE: dict[str, AgentState] = {}


def _draft_node(state: AgentState) -> AgentState:
    generated = generate_draft(
        state["doc_type"],
        state["extracted_text"],
        state["client_name"],
    )
    if "error" in generated:
        return {"error": generated["error"]}

    draft = generated["draft"]
    return {
        "draft": draft,
        "current_draft": draft,
        "assistant_message": "I prepared a draft for CA review and a verification checklist.",
    }


def _checklist_node(state: AgentState) -> AgentState:
    generated = generate_checklist(
        state["doc_type"],
        state["extracted_text"],
        state["client_name"],
    )
    if "error" in generated:
        return {"error": generated["error"]}

    return {"checklist": generated["checklist"]}


def _revision_node(state: AgentState) -> AgentState:
    generated = revise_draft(
        state["doc_type"],
        state["extracted_text"],
        state["client_name"],
        state["current_draft"],
        state["user_message"],
    )
    if "error" in generated:
        return {"error": generated["error"]}

    draft = generated["draft"]
    return {
        "draft": draft,
        "current_draft": draft,
        "assistant_message": "I revised the draft for CA review based on your instruction.",
    }


def _route_start(state: AgentState) -> str:
    return "revision" if state.get("mode") == "revise" else "draft"


def _route_after_draft(state: AgentState) -> str:
    return END if state.get("error") else "checklist"


def _route_after_revision(state: AgentState) -> str:
    return END


def _build_graph() -> Any:
    workflow = StateGraph(AgentState)
    workflow.add_node("draft", _draft_node)
    workflow.add_node("checklist", _checklist_node)
    workflow.add_node("revision", _revision_node)
    workflow.add_conditional_edges(
        START,
        _route_start,
        {"draft": "draft", "revision": "revision"},
    )
    workflow.add_conditional_edges(
        "draft",
        _route_after_draft,
        {"checklist": "checklist", END: END},
    )
    workflow.add_conditional_edges(
        "revision",
        _route_after_revision,
        {END: END},
    )
    workflow.add_edge("checklist", END)
    return workflow.compile(checkpointer=InMemorySaver())


AGENT_GRAPH = _build_graph()


def start_document_session(
    session_id: str,
    client_name: str,
    doc_type: str,
    extracted_text: str,
) -> AgentState:
    """Run the initial document drafting graph and persist session state."""
    state: AgentState = {
        "mode": "draft",
        "session_id": session_id,
        "client_name": client_name,
        "doc_type": doc_type,
        "extracted_text": extracted_text,
    }
    result = AGENT_GRAPH.invoke(
        state,
        config={"configurable": {"thread_id": session_id}},
    )
    stored = {**state, **result}
    SESSION_STORE[session_id] = stored
    return stored


def continue_document_session(session_id: str, user_message: str) -> AgentState:
    """Revise the current draft using the prior session context."""
    previous = SESSION_STORE.get(session_id)
    if not previous:
        return {"error": "Session not found. Upload a document before chatting."}
    if not previous.get("current_draft"):
        return {"error": "No draft is available for revision in this session."}

    state: AgentState = {
        **previous,
        "mode": "revise",
        "user_message": user_message,
    }
    result = AGENT_GRAPH.invoke(
        state,
        config={"configurable": {"thread_id": session_id}},
    )
    stored = {**state, **result}
    SESSION_STORE[session_id] = stored
    return stored

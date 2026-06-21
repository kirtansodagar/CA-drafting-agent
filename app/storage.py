"""SQLite persistence for CA drafting cases."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ca_agent.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create case persistence tables when they do not exist."""
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                client_name TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                extracted_text TEXT NOT NULL,
                draft TEXT NOT NULL,
                checklist TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'review_required',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            );
            """
        )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _message_rows(case_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE case_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_or_replace_case(
    *,
    session_id: str,
    client_name: str,
    doc_type: str,
    filename: str,
    char_count: int,
    extracted_text: str,
    draft: str,
    checklist: str,
    assistant_message: str,
) -> dict[str, Any]:
    """Persist an initial agent result for a session."""
    case_id = str(uuid.uuid4())
    with _connect() as connection:
        existing = connection.execute(
            "SELECT id FROM cases WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if existing:
            case_id = existing["id"]
            connection.execute("DELETE FROM messages WHERE case_id = ?", (case_id,))

        connection.execute(
            """
            INSERT INTO cases (
                id, session_id, client_name, doc_type, filename, char_count,
                extracted_text, draft, checklist, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                client_name = excluded.client_name,
                doc_type = excluded.doc_type,
                filename = excluded.filename,
                char_count = excluded.char_count,
                extracted_text = excluded.extracted_text,
                draft = excluded.draft,
                checklist = excluded.checklist,
                status = 'review_required',
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                case_id,
                session_id,
                client_name,
                doc_type,
                filename,
                char_count,
                extracted_text,
                draft,
                checklist,
            ),
        )
        connection.execute(
            "INSERT INTO messages (id, case_id, role, content) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), case_id, "assistant", assistant_message),
        )

    return get_case(case_id) or {}


def append_case_revision(
    *,
    session_id: str,
    user_message: str,
    assistant_message: str,
    draft: str,
    checklist: str,
) -> dict[str, Any]:
    """Persist a user revision request and the updated draft."""
    case_row = get_case_by_session(session_id)
    if not case_row:
        return {}

    case_id = case_row["id"]
    with _connect() as connection:
        connection.execute(
            """
            UPDATE cases
            SET draft = ?, checklist = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (draft, checklist, case_id),
        )
        connection.execute(
            "INSERT INTO messages (id, case_id, role, content) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), case_id, "user", user_message),
        )
        connection.execute(
            "INSERT INTO messages (id, case_id, role, content) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), case_id, "assistant", assistant_message),
        )

    return get_case(case_id) or {}


def list_cases() -> list[dict[str, Any]]:
    """Return saved cases in most-recent-first order."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, session_id, client_name, doc_type, filename, char_count,
                   draft, checklist, status, created_at, updated_at
            FROM cases
            ORDER BY updated_at DESC, rowid DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_case(case_id: str) -> dict[str, Any] | None:
    """Return a saved case and its chat messages."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, session_id, client_name, doc_type, filename, char_count,
                   extracted_text, draft, checklist, status, created_at, updated_at
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()
    case = _row_to_dict(row)
    if not case:
        return None
    case["messages"] = _message_rows(case_id)
    return case


def get_case_by_session(session_id: str) -> dict[str, Any] | None:
    """Return a saved case by agent session id."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM cases
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return get_case(row["id"])

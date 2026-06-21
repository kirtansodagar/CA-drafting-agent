"""FastAPI application routes for the CA Document Drafter backend."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent import (
    continue_document_session,
    restore_document_session,
    start_document_session,
)
from app.config import MAX_UPLOAD_BYTES, get_allowed_origins, get_app_api_key
from app.generator import MODEL_NAME, generate_draft
from app.parser import parse_document
from app.storage import (
    append_case_revision,
    create_or_replace_case,
    get_case,
    get_case_by_session,
    init_db,
    list_cases,
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="CA Document Drafter", version="1.0.0")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require the configured shared API key for state-changing endpoints."""
    expected_key = get_app_api_key()
    if not expected_key:
        raise HTTPException(status_code=500, detail="APP_API_KEY is not configured.")
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _ensure_upload_dir() -> None:
    """Create the temporary upload directory when it does not already exist."""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not prepare upload directory: {exc}",
        ) from exc


async def _save_upload(file: UploadFile) -> Path:
    """Save an uploaded PDF to temporary storage with a UUID-prefixed filename."""
    _ensure_upload_dir()
    safe_filename = os.path.basename(file.filename or "uploaded.pdf")
    target_path = UPLOAD_DIR / f"{uuid.uuid4()}_{safe_filename}"

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty.")
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("Uploaded PDF exceeds the 25 MB limit.")
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("Uploaded file is not a valid PDF.")

        with open(target_path, "wb") as destination:
            destination.write(file_bytes)

        return target_path
    except Exception as exc:
        try:
            if target_path.exists():
                target_path.unlink()
        except Exception as cleanup_exc:
            print(f"Warning: failed to delete partial upload {target_path}: {cleanup_exc}")
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _delete_uploaded_file(file_path: Path) -> None:
    """Delete a temporary uploaded file after processing finishes."""
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        print(f"Warning: failed to delete uploaded file {file_path}: {exc}")


@app.get("/health")
def health() -> dict[str, str]:
    """Return the API health status and configured Groq model name."""
    return {"status": "ok", "model": MODEL_NAME}


@app.get("/cases")
def cases(_: None = Depends(require_api_key)) -> dict[str, Any]:
    """Return persisted drafting cases."""
    return {"cases": list_cases()}


@app.get("/cases/{case_id}")
def case_detail(case_id: str, _: None = Depends(require_api_key)) -> dict[str, Any]:
    """Return a persisted drafting case with messages."""
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return {"case": case}


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    client_name: str = Form(...),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Accept a PDF upload, parse it, generate a draft letter, and clean up the file."""
    if not client_name.strip():
        raise HTTPException(status_code=422, detail="Client name is required.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported.")

    saved_path: Path | None = None

    try:
        saved_path = await _save_upload(file)
        parsed_document = parse_document(str(saved_path))

        if "error" in parsed_document:
            raise HTTPException(status_code=422, detail=parsed_document["error"])

        generated = generate_draft(
            parsed_document["doc_type"],
            parsed_document["text"],
            client_name.strip(),
        )

        if "error" in generated:
            raise HTTPException(status_code=422, detail=generated["error"])

        return {
            "draft": generated["draft"],
            "doc_type": generated["doc_type"],
            "client_name": generated["client_name"],
            "char_count": parsed_document["char_count"],
            "filename": parsed_document["file_name"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if saved_path is not None:
            _delete_uploaded_file(saved_path)


@app.post("/agent/message")
async def agent_message(
    session_id: str = Form(...),
    message: str = Form(""),
    client_name: str = Form(""),
    consent: bool = Form(False),
    file: UploadFile | None = File(default=None),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Run the CA drafting agent for uploads or follow-up revision messages."""
    if not session_id.strip():
        raise HTTPException(status_code=422, detail="Session ID is required.")

    if file is not None:
        if not consent:
            raise HTTPException(
                status_code=422,
                detail="Consent is required before sending extracted text to Groq.",
            )
        if not client_name.strip():
            raise HTTPException(status_code=422, detail="Client name is required.")
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=422, detail="Only PDF uploads are supported.")

        saved_path: Path | None = None
        try:
            saved_path = await _save_upload(file)
            parsed_document = parse_document(str(saved_path))

            if "error" in parsed_document:
                raise HTTPException(status_code=422, detail=parsed_document["error"])

            result = start_document_session(
                session_id=session_id.strip(),
                client_name=client_name.strip(),
                doc_type=parsed_document["doc_type"],
                extracted_text=parsed_document["text"],
            )

            if "error" in result:
                raise HTTPException(status_code=422, detail=result["error"])

            case = create_or_replace_case(
                session_id=session_id.strip(),
                client_name=client_name.strip(),
                doc_type=result.get("doc_type", parsed_document["doc_type"]),
                filename=parsed_document["file_name"],
                char_count=parsed_document["char_count"],
                extracted_text=parsed_document["text"],
                draft=result.get("draft", ""),
                checklist=result.get("checklist", ""),
                assistant_message=result.get("assistant_message", ""),
            )

            return {
                "case_id": case.get("id", ""),
                "session_id": session_id.strip(),
                "assistant_message": result.get("assistant_message", ""),
                "draft": result.get("draft", ""),
                "checklist": result.get("checklist", ""),
                "doc_type": result.get("doc_type", "unknown"),
                "client_name": result.get("client_name", client_name.strip()),
                "char_count": parsed_document["char_count"],
                "filename": parsed_document["file_name"],
                "review_required": True,
            }
        finally:
            if saved_path is not None:
                _delete_uploaded_file(saved_path)

    if not message.strip():
        raise HTTPException(status_code=422, detail="Message is required.")

    result = continue_document_session(session_id.strip(), message.strip())
    if "error" in result and "Session not found" in result["error"]:
        saved_case = get_case_by_session(session_id.strip())
        if saved_case:
            restore_document_session(
                session_id=saved_case["session_id"],
                client_name=saved_case["client_name"],
                doc_type=saved_case["doc_type"],
                extracted_text=saved_case["extracted_text"],
                current_draft=saved_case["draft"],
                checklist=saved_case["checklist"],
            )
            result = continue_document_session(session_id.strip(), message.strip())

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    case = append_case_revision(
        session_id=session_id.strip(),
        user_message=message.strip(),
        assistant_message=result.get("assistant_message", ""),
        draft=result.get("draft", ""),
        checklist=result.get("checklist", ""),
    )

    return {
        "case_id": case.get("id", ""),
        "session_id": session_id.strip(),
        "assistant_message": result.get("assistant_message", ""),
        "draft": result.get("draft", ""),
        "checklist": result.get("checklist", ""),
        "doc_type": result.get("doc_type", "unknown"),
        "client_name": result.get("client_name", ""),
        "review_required": True,
    }


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

"""Runtime configuration for the CA drafting agent."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = "http://localhost:8501,http://127.0.0.1:8501"


def get_app_api_key() -> str | None:
    """Return the shared API key required for backend write operations."""
    return os.getenv("APP_API_KEY")


def get_allowed_origins() -> list[str]:
    """Return configured CORS origins for local frontend clients."""
    raw_origins = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

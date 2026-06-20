"""PDF parsing and document type detection utilities."""

from __future__ import annotations

import os
import re
from typing import Any

import fitz


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from every page of a PDF file using PyMuPDF."""
    document = None

    try:
        document = fitz.open(file_path)
        page_text = []

        for page in document:
            page_text.append(page.get_text())

        extracted_text = "\n".join(page_text).strip()

        if len(extracted_text) < 100:
            raise ValueError(
                "PDF appears to be scanned/image-based. Text extraction failed."
            )

        return extracted_text
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to extract text from PDF: {exc}") from exc
    finally:
        if document is not None:
            try:
                document.close()
            except Exception as exc:
                print(f"Warning: failed to close PDF document: {exc}")


def detect_doc_type(text: str) -> str:
    """Detect whether extracted text is Form 26AS, a tax notice, an ITR summary, or unknown."""
    normalized_text = text.lower()

    if re.search(r"\bform\s*26as\b|annual tax statement|\btraces\b", normalized_text):
        return "form_26as"

    if re.search(
        r"income tax notice|section\s+143|section\s+148|demand notice",
        normalized_text,
    ):
        return "tax_notice"

    if re.search(r"return of income|acknowledgement number|\bitr-", normalized_text):
        return "itr_summary"

    return "unknown"


def clean_text(text: str) -> str:
    """Normalize whitespace in extracted PDF text while preserving paragraph breaks."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def parse_document(file_path: str) -> dict[str, Any]:
    """Parse a PDF file and return detected metadata plus cleaned source text."""
    try:
        raw_text = extract_text_from_pdf(file_path)
        cleaned_text = clean_text(raw_text)
        doc_type = detect_doc_type(cleaned_text)

        return {
            "doc_type": doc_type,
            "text": cleaned_text,
            "char_count": len(cleaned_text),
            "file_name": os.path.basename(file_path),
        }
    except Exception as exc:
        return {"error": str(exc)}

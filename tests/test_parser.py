"""Tests for PDF parsing and document detection helpers."""

from unittest.mock import MagicMock, patch

from app.parser import clean_text, detect_doc_type, parse_document


def test_detect_doc_type_form_26as() -> None:
    """Detect Form 26AS text using TRACES wording."""
    assert detect_doc_type("Annual Tax Statement downloaded from TRACES") == "form_26as"


def test_detect_doc_type_tax_notice() -> None:
    """Detect Income Tax Notice text using a section reference."""
    assert detect_doc_type("Notice under Section 143 from Income Tax Department") == "tax_notice"


def test_detect_doc_type_itr_summary() -> None:
    """Detect ITR summary text using acknowledgement wording."""
    assert detect_doc_type("Return of Income with Acknowledgement Number 12345") == "itr_summary"


def test_detect_doc_type_unknown() -> None:
    """Return unknown when no document type markers are present."""
    assert detect_doc_type("A generic financial statement without tax markers") == "unknown"


def test_clean_text_collapses_messy_whitespace() -> None:
    """Collapse repeated spaces and excessive blank lines in extracted text."""
    messy_text = "  Line one   with spaces\n\n\n\nLine two\t\twith tabs  "
    assert clean_text(messy_text) == "Line one with spaces\n\nLine two with tabs"


@patch("app.parser.fitz.open")
def test_parse_document_with_mock_fitz(mock_open: MagicMock) -> None:
    """Parse a mocked PDF document and return cleaned metadata."""
    page = MagicMock()
    page.get_text.return_value = (
        "Form 26AS Annual Tax Statement from TRACES. "
        "This mocked text is intentionally longer than one hundred characters "
        "so extraction validation succeeds."
    )

    document = MagicMock()
    document.__iter__.return_value = iter([page])
    mock_open.return_value = document

    parsed = parse_document("sample.pdf")

    assert parsed["doc_type"] == "form_26as"
    assert parsed["file_name"] == "sample.pdf"
    assert parsed["char_count"] == len(parsed["text"])
    document.close.assert_called_once()

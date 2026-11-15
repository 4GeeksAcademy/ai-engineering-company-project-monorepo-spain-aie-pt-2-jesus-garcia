"""Integración de la conversión PDF→Markdown con los PDFs del briefing."""

from __future__ import annotations

import pytest

from data.pipelines.rfp_intake.ingest import (
    DocumentConversionError,
    convert_pdf_to_markdown,
    is_pdf_bytes,
)
from rfp_support import channel_paths


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, "ModaViva"),
        (1, "Luna Cosmetics"),
        (2, "RapidShip"),
    ],
)
def test_sample_pdfs_convert_to_markdown(tmp_path, index, expected):
    pytest.importorskip("markitdown")
    pdf = channel_paths()[index]
    result = convert_pdf_to_markdown(pdf, tmp_path / f"{pdf.stem}.md")

    assert expected.lower() in result["markdown"].lower()
    assert result["document_metadata"]["page_count"] >= 1
    assert result["document_metadata"]["converter"] == "markitdown"
    assert (tmp_path / f"{pdf.stem}.md").exists()


def test_non_pdf_is_rejected(tmp_path):
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"no soy un pdf")
    with pytest.raises(DocumentConversionError):
        convert_pdf_to_markdown(path, tmp_path / "notes.md")


def test_is_pdf_bytes_checks_header():
    assert is_pdf_bytes(b"%PDF-1.7\n") is True
    assert is_pdf_bytes(b"<html>") is False

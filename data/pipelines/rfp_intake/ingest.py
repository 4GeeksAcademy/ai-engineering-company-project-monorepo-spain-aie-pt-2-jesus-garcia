"""Ingesta de la RFP: PDF → Markdown antes de que lo lea cualquier agente."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:  # pragma: no cover - el import se prueba en el entorno real/Docker
    from markitdown import MarkItDown
except ImportError:  # pragma: no cover
    MarkItDown = None  # type: ignore[assignment]

try:  # pragma: no cover
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]


class DocumentConversionError(RuntimeError):
    """El PDF no se pudo convertir a un Markdown con texto utilizable."""


def is_pdf_bytes(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_metadata(pdf_path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "file_name": pdf_path.name,
        "file_size_bytes": pdf_path.stat().st_size,
        "sha256": sha256_file(pdf_path),
        "page_count": None,
        "title": None,
        "author": None,
        "creator": None,
        "producer": None,
        "converter": "markitdown",
    }
    if PdfReader is None:
        return metadata
    try:
        reader = PdfReader(str(pdf_path))
        metadata["page_count"] = len(reader.pages)
        info = reader.metadata or {}
        metadata["title"] = getattr(info, "title", None)
        metadata["author"] = getattr(info, "author", None)
        metadata["creator"] = getattr(info, "creator", None)
        metadata["producer"] = getattr(info, "producer", None)
    except Exception:  # pragma: no cover - un PDF raro no debe romper la ingesta
        pass
    return metadata


def _markdown_from_result(result: Any) -> str:
    for attribute in ("markdown", "text_content", "text"):
        value = getattr(result, attribute, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def convert_pdf_to_markdown(pdf_path: Path, markdown_path: Path) -> dict:
    """Convierte un PDF y devuelve ``markdown`` + metadatos del documento.

    Lanza :class:`DocumentConversionError` si el PDF no tiene texto extraíble:
    un PDF escaneado no se descarta como "no RFP", se marca como error para que
    Ventas pueda revisarlo.
    """

    if MarkItDown is None:
        raise DocumentConversionError(
            "MarkItDown no está instalado; instala markitdown[pdf] en el backend."
        )
    if not pdf_path.exists():
        raise DocumentConversionError(f"No existe el PDF: {pdf_path}")
    if not is_pdf_bytes(pdf_path.read_bytes()[:5]):
        raise DocumentConversionError("El archivo no tiene cabecera PDF válida.")

    try:
        result = MarkItDown().convert(str(pdf_path))
    except Exception as exc:
        raise DocumentConversionError(
            f"MarkItDown no pudo convertir el PDF: {exc}"
        ) from exc

    markdown = _markdown_from_result(result).replace("\r\n", "\n").strip()
    title = getattr(result, "title", None)
    if (
        isinstance(title, str)
        and title.strip()
        and title.strip().lower() not in markdown[:400].lower()
    ):
        markdown = f"# {title.strip()}\n\n{markdown}"
    if len(markdown) < 50:
        raise DocumentConversionError(
            "El PDF no contiene texto extraíble suficiente (¿es un escaneo?)."
        )

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")

    document_metadata = _document_metadata(pdf_path)
    document_metadata["markdown_chars"] = len(markdown)
    return {
        "markdown": markdown,
        "markdown_path": str(markdown_path),
        "document_metadata": document_metadata,
    }

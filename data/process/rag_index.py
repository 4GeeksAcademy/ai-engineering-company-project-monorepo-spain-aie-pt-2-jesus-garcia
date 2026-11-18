"""Chunking, embeddings e indexación de la base de conocimiento de TrackFlow."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import math
import re
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

from data.process.rag_config import (
    COLLECTION_NAME,
    COMPANY,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    LANGUAGE,
    LLM_API_KEY,
    LLM_BASE_URL,
    MAX_CHUNK_CHARS,
    MIN_CHUNKS_PER_DOCUMENT,
    SOURCE_DOCUMENTS,
    TARGET_CHUNK_CHARS,
    KNOWLEDGE_BASE_DIR,
    RagError,
    build_api_url,
    build_model_url,
    validate_distinct_models,
    validate_llm_config,
)

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    source_document: str
    title: str
    text: str


@dataclass(frozen=True)
class Chunk:
    source_document: str
    section: str
    chunk_index: int
    text: str

    @property
    def embedding_text(self) -> str:
        return f"{self.section}\n\n{self.text}".strip()

    def payload(self) -> dict:
        return {
            "company": COMPANY,
            "source_document": self.source_document,
            "section": self.section,
            "language": LANGUAGE,
            "chunk_index": self.chunk_index,
            "text": self.text,
        }

    def point_id(self) -> str:
        digest = hashlib.sha1(self.text.encode("utf-8")).hexdigest()
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{COMPANY}:{self.source_document}:{self.chunk_index}:{digest}",
            )
        )


def load_source_documents() -> list[SourceDocument]:
    """Lee los cuatro documentos fuente del BRIEFING desde docs/company-knowledge-base/."""
    documents: list[SourceDocument] = []
    for filename, slug in SOURCE_DOCUMENTS.items():
        path = KNOWLEDGE_BASE_DIR / filename
        if not path.exists():
            raise RagError(f"No existe el documento fuente: {path}")
        text = path.read_text(encoding="utf-8")
        title = _document_title(text, path)
        documents.append(
            SourceDocument(
                path=path,
                source_document=slug,
                title=title,
                text=text,
            )
        )
    return documents


def _document_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            return match.group(2).strip()
    return path.stem


def chunk_document(document: SourceDocument) -> list[Chunk]:
    """Divide un documento por encabezados y bloques semánticos."""
    chunks: list[Chunk] = []
    for section, body_lines in _split_sections(document.text, document.title):
        blocks = _merge_blocks(
            _split_body_into_blocks(body_lines),
            TARGET_CHUNK_CHARS,
        )
        for block in blocks:
            for part in _split_long_block(block, MAX_CHUNK_CHARS):
                text = part.strip()
                if not text:
                    continue
                chunks.append(
                    Chunk(
                        source_document=document.source_document,
                        section=section,
                        chunk_index=len(chunks),
                        text=text,
                    )
                )
    return chunks


def _split_sections(text: str, fallback_title: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_section = fallback_title
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append((current_section, current_lines))
            current_lines = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            flush()
            current_section = match.group(2).strip()
            continue
        current_lines.append(line)
    flush()
    return sections


def _split_body_into_blocks(body_lines: list[str]) -> list[str]:
    blocks: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    current_item: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        if text:
            blocks.append(text)
        paragraph_lines = []

    def flush_item() -> None:
        nonlocal current_item
        text = " ".join(line.strip() for line in current_item if line.strip())
        if text:
            list_items.append(text)
        current_item = []

    def flush_list() -> None:
        flush_item()
        blocks.extend(_pack_list_items(list_items, TARGET_CHUNK_CHARS))
        list_items.clear()

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            in_list = False
            continue

        if _LIST_ITEM_RE.match(line):
            flush_paragraph()
            flush_item()
            current_item.append(stripped)
            in_list = True
            continue

        if in_list and current_item:
            # Línea de continuación de un ítem de lista (p. ej. una regla
            # partida visualmente en el Markdown).
            current_item.append(stripped)
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    return blocks


def _merge_blocks(blocks: list[str], target_chars: int) -> list[str]:
    """Une introducciones cortas con la lista que presentan, sin cruzar secciones."""
    merged: list[str] = []
    for block in blocks:
        if not merged:
            merged.append(block)
            continue
        previous = merged[-1]
        candidate = f"{previous}\n\n{block}"
        is_list = _LIST_ITEM_RE.match(block) is not None
        previous_is_intro = previous.rstrip().endswith(":")
        previous_is_short = len(previous) <= 250
        if (
            len(candidate) <= target_chars
            and (previous_is_intro or (is_list and previous_is_short))
        ):
            merged[-1] = candidate
        else:
            merged.append(block)
    return merged


def _pack_list_items(items: list[str], target_chars: int) -> list[str]:
    if not items:
        return []
    packed: list[str] = []
    group: list[str] = []
    for item in items:
        candidate = "\n".join([*group, item])
        if group and len(candidate) > target_chars:
            packed.append("\n".join(group))
            group = [item]
        else:
            group.append(item)
    if group:
        packed.append("\n".join(group))
    return packed


def _split_long_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]

    lines = block.splitlines()
    if len(lines) > 1 and all(_LIST_ITEM_RE.match(line) for line in lines):
        packed: list[str] = []
        group: list[str] = []
        for line in lines:
            candidate = "\n".join([*group, line])
            if group and len(candidate) > max_chars:
                packed.append("\n".join(group))
                group = [line]
            else:
                group.append(line)
        if group:
            packed.append("\n".join(group))
        return packed

    sentences = [part for part in _SENTENCE_SPLIT_RE.split(block) if part]
    packed = []
    group = ""
    for sentence in sentences:
        candidate = f"{group} {sentence}".strip()
        if group and len(candidate) > max_chars:
            packed.append(group)
            group = sentence
        else:
            group = candidate
    if group:
        packed.append(group)
    return packed


def post_json(path: str, payload: dict) -> dict:
    validate_llm_config()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    url = build_api_url(LLM_BASE_URL, path)
    model = str(payload.get("model", ""))
    logger.debug(
        "POST %s model=%s model_url=%s",
        url,
        model,
        build_model_url(LLM_BASE_URL, model),
    )
    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                url,
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise RagError(f"No se pudo conectar con el proveedor de IA: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        raise RagError(
            f"El proveedor de IA respondió {response.status_code}: {detail}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise RagError("El proveedor de IA devolvió una respuesta no JSON.") from exc


def _decode_embedding(value: object) -> list[float]:
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        raw = base64.b64decode(value)
        if len(raw) == EMBEDDING_DIM:
            return [float(byte - 256 if byte > 127 else byte) for byte in raw]
        if len(raw) == EMBEDDING_DIM * 4:
            return list(struct.unpack(f"<{EMBEDDING_DIM}f", raw))
        raise RagError(
            f"Embedding base64 con longitud inesperada: {len(raw)} bytes "
            f"(se esperaban {EMBEDDING_DIM} o {EMBEDDING_DIM * 4})."
        )
    raise RagError(f"Formato de embedding no soportado: {type(value).__name__}")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise RagError("El proveedor devolvió un embedding de norma cero.")
    return [value / norm for value in vector]


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embebe una lista de textos en lotes con el modelo de embeddings."""
    if not texts:
        return []
    if any(not text.strip() for text in texts):
        raise RagError("No se pueden embeber textos vacíos.")
    if batch_size < 1:
        raise RagError("batch_size debe ser mayor que cero.")

    validate_llm_config()
    validate_distinct_models()

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        data = post_json(
            "embeddings",
            {"model": EMBEDDING_MODEL, "input": batch},
        )
        items = data.get("data")
        if not isinstance(items, list) or len(items) != len(batch):
            raise RagError("La respuesta de embeddings no tiene el tamaño esperado.")
        items = sorted(items, key=lambda item: item.get("index", 0))
        for item in items:
            vector = _normalize(_decode_embedding(item["embedding"]))
            if len(vector) != EMBEDDING_DIM:
                raise RagError(
                    f"Embedding de {len(vector)} dimensiones; se esperaban "
                    f"{EMBEDDING_DIM}."
                )
            vectors.append(vector)
    return vectors


def embed(text: str) -> list[float]:
    """Vector de un texto (misma función al indexar y al consultar)."""
    return embed_batch([text])[0]


def get_qdrant_client():
    """Cliente Qdrant perezoso (evita dependencia en tests con stub)."""
    from qdrant_client import QdrantClient

    from data.process.rag_config import QDRANT_API_KEY, QDRANT_URL

    if QDRANT_URL == ":memory:":
        return QdrantClient(location=":memory:")
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def setup(*, recreate: bool = True) -> dict:
    """Indexa los cuatro documentos fuente en la colección trackflow_knowledge.

    Idempotencia: por defecto se borra y recrea la colección (clean-and-reload)
    y los IDs de punto son UUID5 deterministas a partir del texto.
    """
    from qdrant_client.http import models as qdrant_models

    documents = load_source_documents()
    chunks: list[Chunk] = []
    by_document: dict[str, int] = {}

    for document in documents:
        document_chunks = chunk_document(document)
        if len(document_chunks) < MIN_CHUNKS_PER_DOCUMENT:
            raise RagError(
                f"{document.source_document} produjo {len(document_chunks)} chunks; "
                f"el mínimo es {MIN_CHUNKS_PER_DOCUMENT}."
            )
        chunks.extend(document_chunks)
        by_document[document.source_document] = len(document_chunks)

    vectors = embed_batch([chunk.embedding_text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise RagError("El número de embeddings no coincide con el de chunks.")

    client = get_qdrant_client()
    if recreate and client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qdrant_models.VectorParams(
                size=EMBEDDING_DIM,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    points = [
        qdrant_models.PointStruct(
            id=chunk.point_id(),
            vector=vector,
            payload=chunk.payload(),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    for start in range(0, len(points), 64):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[start : start + 64],
            wait=True,
        )

    stats = {
        "collection": COLLECTION_NAME,
        "documents": len(documents),
        "chunks": len(chunks),
        "by_document": by_document,
    }
    logger.info("Indexación completada: %s", stats)
    return stats


def _dry_run_stats() -> dict:
    documents = load_source_documents()
    by_document: dict[str, int] = {}
    total = 0
    for document in documents:
        count = len(chunk_document(document))
        by_document[document.source_document] = count
        total += count
    return {
        "collection": COLLECTION_NAME,
        "documents": len(documents),
        "chunks": total,
        "by_document": by_document,
        "dry_run": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Indexa la base de conocimiento de TrackFlow en Qdrant."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo calcula chunks y estadísticas, sin llamar a embeddings ni Qdrant.",
    )
    parser.add_argument(
        "--no-recreate",
        action="store_true",
        help="No borra la colección antes de indexar (upsert por IDs deterministas).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    stats = _dry_run_stats() if args.dry_run else setup(recreate=not args.no_recreate)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

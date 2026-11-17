"""Política de audiencia del RAG.

La colección ``trackflow_knowledge`` mezcla documentos públicos (políticas de
devolución y SLA) con documentación comercial interna (tarifas de
almacenamiento y cobertura/decisiones de carriers). El índice no distingue
audiencias, así que la separación se aplica en la capa de servicio: un usuario
final solo recibe los documentos públicos; manager/admin reciben todo.

Los slugs coinciden con ``SOURCE_DOCUMENTS`` de ``data/process/rag_config.py``.
"""

from __future__ import annotations

import os

PUBLIC_DOCUMENT_SLUGS = ("sla-delivery", "returns-policy")
INTERNAL_DOCUMENT_SLUGS = ("storage-pricing", "carrier-coverage")

_MANAGER_ROLES = {"admin", "manager"}


def _csv_env(name: str, default: tuple[str, ...]) -> frozenset[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return frozenset(default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def public_documents() -> frozenset[str]:
    return _csv_env("RAG_PUBLIC_DOCUMENTS", PUBLIC_DOCUMENT_SLUGS)


def internal_documents() -> frozenset[str]:
    return _csv_env("RAG_INTERNAL_DOCUMENTS", INTERNAL_DOCUMENT_SLUGS)


def allowed_documents(role: str | None) -> frozenset[str] | None:
    """Documentos permitidos. ``None`` significa "sin filtro" (manager/admin)."""

    normalized = (role or "").strip().lower()
    if normalized in _MANAGER_ROLES:
        return None
    if normalized == "user":
        return public_documents()
    # Rol desconocido (scripts internos/tests heredados): no se filtra. En
    # producción todo request autenticado lleva rol (default "user").
    return None


def filter_context_for_role(
    context: list[dict],
    role: str | None,
) -> list[dict]:
    """Elimina del contexto los documentos que el rol no puede ver."""

    allowed = allowed_documents(role)
    if allowed is None:
        return list(context)
    filtered: list[dict] = []
    for item in context:
        source = str(item.get("source_document") or "").strip()
        if source in allowed:
            filtered.append(item)
    return filtered


__all__ = [
    "INTERNAL_DOCUMENT_SLUGS",
    "PUBLIC_DOCUMENT_SLUGS",
    "allowed_documents",
    "filter_context_for_role",
    "internal_documents",
    "public_documents",
]

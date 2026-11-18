"""Llamada JSON al LLM de generación (OpenAI-compatible) y parser tolerante."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from data.process.rag_config import (
    GENERATION_MODEL,
    RagError,
    validate_distinct_models,
    validate_llm_config,
)

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_content(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RagError("El proveedor de generación no devolvió ninguna respuesta.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise RagError("El proveedor de generación devolvió una respuesta vacía.")
    return content.strip()


def _raw_chat_completion(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    payload = {
        "model": GENERATION_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Se reutiliza el transporte del RAG para no duplicar autenticación,
    # normalización de URL ni manejo de errores del proveedor.
    from data.process.rag_index import post_json

    return _extract_content(post_json("chat/completions", payload))


def parse_json_object(content: str) -> dict | None:
    """Extrae el primer objeto JSON de una respuesta, aunque venga con texto."""

    if not content:
        return None
    cleaned = _FENCE_RE.sub("", content.strip()).strip()
    candidates = [cleaned]
    start = cleaned.find("{")
    if start > 0:
        candidates.append(cleaned[start:])
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            value, _ = decoder.raw_decode(candidate)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def chat_json(
    messages: list[dict],
    *,
    max_tokens: int = 1_000,
    temperature: float = 0.1,
) -> tuple[dict | None, str]:
    """Devuelve ``(objeto, contenido_crudo)``. Nunca lanza por JSON inválido."""

    validate_llm_config()
    validate_distinct_models()
    content = _raw_chat_completion(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    parsed = parse_json_object(content)
    if parsed is None:
        logger.warning(
            "El LLM no devolvió un JSON válido para memoria; se usa fallback."
        )
    return parsed, content


def _looks_like_json(content: str) -> bool:
    return content.strip().startswith(("{", "["))


def json_or_raw_answer(content: str) -> str:
    """Respuesta de emergencia cuando el JSON no se puede parsear.

    Si el contenido parece JSON pero está roto, se prefiere un mensaje honesto
    antes que enseñar llaves al usuario. En cualquier otro caso se devuelve el
    texto tal cual (el modelo ignoró el formato pero respondió).
    """

    if _looks_like_json(content):
        return (
            "No pude completar la respuesta en este momento. "
            "Inténtalo de nuevo en unos minutos."
        )
    return content.strip()


__all__ = [
    "chat_json",
    "json_or_raw_answer",
    "parse_json_object",
]

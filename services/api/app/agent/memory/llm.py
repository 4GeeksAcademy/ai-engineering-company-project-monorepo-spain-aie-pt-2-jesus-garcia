"""Llamada JSON al LLM de generación (OpenAI-compatible) y parser tolerante."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Iterable
from typing import Any

import httpx

from data.process.rag_config import (
    GENERATION_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    RagError,
    build_api_url,
    validate_distinct_models,
    validate_llm_config,
)

from ..streaming import GenerationAborted
from .streaming import AnswerStreamExtractor

logger = logging.getLogger(__name__)

TokenCallback = Callable[[str], None]

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


def _delta_content(chunk: dict) -> str:
    """Texto de un chunk SSE ``chat.completion.chunk``; "" si no aporta."""

    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta") or {}
    content = delta.get("content") if isinstance(delta, dict) else None
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    return content if isinstance(content, str) else ""


def _consume_stream_lines(
    lines: Iterable[str],
    *,
    extractor: AnswerStreamExtractor,
    on_token: TokenCallback | None,
    abort: threading.Event | None,
) -> list[str]:
    raw_parts: list[str] = []
    for line in lines:
        if abort is not None and abort.is_set():
            raise GenerationAborted()
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            logger.debug("Chunk SSE no JSON ignorado: %s", payload[:120])
            continue
        if not isinstance(chunk, dict):
            continue
        content = _delta_content(chunk)
        if not content:
            continue
        raw_parts.append(content)
        visible = extractor.feed(content)
        if visible and on_token is not None:
            on_token(visible)
    if abort is not None and abort.is_set():
        raise GenerationAborted()
    return raw_parts


def chat_json_stream(
    messages: list[dict],
    *,
    on_token: TokenCallback | None = None,
    abort: threading.Event | None = None,
    max_tokens: int = 1_000,
    temperature: float = 0.1,
    stream_lines: Iterable[str] | None = None,
) -> tuple[dict | None, str]:
    """Como :func:`chat_json` pero emitiendo la respuesta visible token a token.

    El JSON completo se sigue validando al final; ``on_token`` solo recibe el
    contenido de la cadena ``respuesta``. ``stream_lines`` permite inyectar un
    stream falso en los tests sin red.
    """

    validate_llm_config()
    validate_distinct_models()
    extractor = AnswerStreamExtractor()

    if stream_lines is not None:
        raw_parts = _consume_stream_lines(
            stream_lines,
            extractor=extractor,
            on_token=on_token,
            abort=abort,
        )
    else:
        payload = {
            "model": GENERATION_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        }
        url = build_api_url(LLM_BASE_URL, "chat/completions")
        try:
            with httpx.Client(timeout=90.0) as client:
                with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        detail = response.read().decode(
                            "utf-8", errors="replace"
                        )[:500]
                        raise RagError(
                            "El proveedor de IA respondió "
                            f"{response.status_code}: {detail}"
                        )
                    raw_parts = _consume_stream_lines(
                        response.iter_lines(),
                        extractor=extractor,
                        on_token=on_token,
                        abort=abort,
                    )
        except httpx.HTTPError as exc:
            raise RagError(
                f"No se pudo conectar con el proveedor de IA: {exc}"
            ) from exc

    content = "".join(raw_parts)
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
    "chat_json_stream",
    "json_or_raw_answer",
    "parse_json_object",
]

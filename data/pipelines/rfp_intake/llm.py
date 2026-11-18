"""Cliente JSON mínimo para los agentes de recepción de RFPs.

Reutiliza el transporte del RAG (autenticación, normalización de URL y manejo
de errores del proveedor) y añade parseo tolerante + un reintento cuando el
modelo no devuelve un objeto JSON válido. No importa nada de ``services/api``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Protocol

from data.process.rag_config import GENERATION_MODEL, RagError
from data.process.rag_index import post_json

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
DEFAULT_TIMEOUT = float(os.getenv("RFP_LLM_TIMEOUT_SECONDS", "90"))


class LlmError(RuntimeError):
    """El proveedor no devolvió un objeto JSON utilizable."""


class JsonLlm(Protocol):
    def __call__(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1_200,
        temperature: float = 0.0,
    ) -> dict: ...


def _extract_content(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmError("El proveedor de IA no devolvió ninguna respuesta.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise LlmError("El proveedor de IA devolvió una respuesta vacía.")
    return content.strip()


def parse_json_object(content: str) -> dict | None:
    """Extrae el primer objeto JSON aunque venga envuelto en texto o fences."""

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


class LlmClient:
    """Implementación por defecto sobre el proxy OpenAI-compatible del RAG."""

    def __init__(self, *, timeout: float | None = None, retries: int = 2) -> None:
        self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        self.retries = retries

    def __call__(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1_200,
        temperature: float = 0.0,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            attempt_messages: list[dict[str, Any]] = list(messages)
            if attempt > 0:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "La respuesta anterior no era un objeto JSON válido. "
                            "Devuelve exclusivamente el objeto JSON pedido, sin "
                            "texto adicional ni bloques de código."
                        ),
                    }
                )
            try:
                payload = {
                    "model": GENERATION_MODEL,
                    "messages": attempt_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                data = post_json(
                    "chat/completions", payload, timeout=self.timeout
                )
                parsed = parse_json_object(_extract_content(data))
                if parsed is None:
                    raise LlmError("La respuesta no contiene un objeto JSON.")
                return parsed
            except (LlmError, RagError) as exc:
                last_error = exc
                logger.warning(
                    "rfp_intake LLM intento %d/%d falló: %s",
                    attempt + 1,
                    self.retries + 1,
                    exc,
                )
        raise LlmError(str(last_error) if last_error else "Fallo del LLM")

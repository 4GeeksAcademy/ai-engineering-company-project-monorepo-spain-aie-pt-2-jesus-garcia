"""Logging estructurado del servidor MCP.

Cada invocación de una tool produce **una** línea JSON con el cliente OAuth, el
sujeto, los scopes, el resultado, el código de error (si lo hubo) y la latencia.
No se registran tokens ni secretos; los argumentos se sanean y se truncan.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

from mcpauth.types import AuthInfo

TOOL_LOGGER_NAME = "trackflow_mcp.tools"
_REDACTED_KEYS = {"token", "access_token", "authorization", "secret", "password"}
_MAX_STRING = 200


class JsonFormatter(logging.Formatter):
    """Formatter que emite una línea JSON por registro."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, Any]
        try:
            parsed = json.loads(message)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
            payload.setdefault(
                "timestamp",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            payload.setdefault("level", record.levelname)
        else:
            payload = {
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # uvicorn instala sus propios handlers; que propaguen al root configurado.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in _REDACTED_KEYS):
                cleaned[key] = "***"
            else:
                cleaned[key] = _sanitize(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + "…"
    return value


def sanitize_arguments(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return _sanitize(arguments or {})


def log_tool_call(
    *,
    tool: str,
    auth_info: AuthInfo | None,
    arguments: dict[str, Any] | None,
    outcome: str,
    error_code: str | None = None,
    duration_ms: float | None = None,
    backend_status: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event": "tool_invocation",
        "tool": tool,
        "client_id": getattr(auth_info, "client_id", None),
        "subject": getattr(auth_info, "subject", None),
        "scopes": list(getattr(auth_info, "scopes", []) or []),
        "outcome": outcome,
        "error_code": error_code,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "arguments": sanitize_arguments(arguments),
    }
    if backend_status is not None:
        payload["backend_status"] = backend_status
    if extra:
        payload.update(extra)
    logging.getLogger(TOOL_LOGGER_NAME).info(
        json.dumps(payload, ensure_ascii=False, default=str)
    )


class Timer:
    """Context manager mínimo para medir latencia en milisegundos."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.elapsed_ms = 0.0

    def stop(self) -> float:
        self.elapsed_ms = (time.perf_counter() - self.started) * 1000.0
        return self.elapsed_ms


__all__ = [
    "JsonFormatter",
    "TOOL_LOGGER_NAME",
    "Timer",
    "configure_logging",
    "log_tool_call",
    "sanitize_arguments",
]

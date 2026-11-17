"""Códigos de error del servidor MCP y su traducción a errores de tool.

Hay tres capas de error, deliberadamente distintas:

* **401/403 HTTP** — los produce ``mcpauth`` antes de entrar en el servidor MCP
  (token ausente, firma/issuer/audiencia inválidos o falta el scope base).
* **Errores de tool** — ``ToolError`` de FastMCP, con un cuerpo JSON que incluye
  ``error_code``. El cliente MCP los ve con ``isError: true``.
* **Errores de transporte/validación del protocolo** — JSON-RPC ``-32602`` para
  argumentos que no cumplen el esquema de la tool.

Este módulo centraliza los códigos de la segunda y tercera capa.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError


class ErrorCode(StrEnum):
    """Códigos estables expuestos por las tools del servidor."""

    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
    INVENTORY_READ_ONLY = "INVENTORY_READ_ONLY"
    BACKEND_AUTH_FAILED = "BACKEND_AUTH_FAILED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolFailure(Exception):
    """Fallo de dominio controlado que se devuelve como error de tool."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class BackendError(Exception):
    """La API de TrackFlow respondió con un error o no respondió."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        path: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.path = path


def error_payload(
    code: ErrorCode | str,
    message: str,
    *,
    tool: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cuerpo JSON estable que viaja dentro del ``ToolError``."""
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": str(code),
        "message": message,
    }
    if tool:
        payload["tool"] = tool
    if details:
        payload["details"] = details
    return payload


def as_tool_error(
    code: ErrorCode | str,
    message: str,
    *,
    tool: str = "",
    details: dict[str, Any] | None = None,
) -> ToolError:
    """Construye un ``ToolError`` cuyo texto es JSON parseable por el cliente."""
    return ToolError(
        json.dumps(
            error_payload(code, message, tool=tool, details=details),
            ensure_ascii=False,
            default=str,
        )
    )


def raise_tool_error(
    code: ErrorCode | str,
    message: str,
    *,
    tool: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    raise as_tool_error(code, message, tool=tool, details=details)


def map_backend_error(exc: BackendError) -> ToolFailure:
    """Traduce un ``BackendError`` de la API a un fallo de tool."""
    return ToolFailure(exc.code, exc.message, details=exc.details)


def translate_exception(exc: Exception) -> ToolFailure:
    """Convierte cualquier excepción en un ``ToolFailure`` con código estable."""
    if isinstance(exc, ToolFailure):
        return exc
    if isinstance(exc, BackendError):
        return map_backend_error(exc)
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return ToolFailure(
            ErrorCode.BACKEND_TIMEOUT,
            "La API de TrackFlow no respondió dentro del tiempo esperado.",
        )
    if isinstance(exc, httpx.RequestError):
        return ToolFailure(
            ErrorCode.BACKEND_UNAVAILABLE,
            "No se pudo conectar con la API de TrackFlow.",
        )
    if isinstance(exc, ValidationError):
        return ToolFailure(
            ErrorCode.VALIDATION_ERROR,
            "Los argumentos de la tool no cumplen el esquema.",
            details={"errors": exc.errors(include_url=False)},
        )
    return ToolFailure(
        ErrorCode.INTERNAL_ERROR,
        "Error interno inesperado al ejecutar la tool.",
    )


# Códigos HTTP de auth que produce mcpauth. Se documentan aquí para que el
# README y los tests usen exactamente los mismos valores.
AUTH_HTTP_ERRORS = {
    "missing_token": ("invalid_token", 401),
    "invalid_token": ("invalid_token", 401),
    "invalid_issuer": ("invalid_issuer", 401),
    "invalid_audience": ("invalid_audience", 401),
    "missing_required_scopes": ("missing_required_scopes", 403),
}


__all__ = [
    "AUTH_HTTP_ERRORS",
    "BackendError",
    "ErrorCode",
    "ToolFailure",
    "as_tool_error",
    "error_payload",
    "map_backend_error",
    "raise_tool_error",
    "translate_exception",
]

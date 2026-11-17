"""Cliente MCP del agente mediante ``langchain-mcp-adapters``.

Es el **único** camino del agente hacia el Incidents Manager y el inventario:
carga las tools desde el servidor MCP (Streamable HTTP), las invoca con el
contrato tipado de ``contracts.py`` y traduce cualquier fallo a un fallback
honesto. El grafo nunca recibe una excepción de transporte.

Las tools lógicas del agente se mantienen como ``incident_lookup`` /
``inventory_lookup`` para no romper el estado ni los traces; por debajo llaman a
las tools MCP ``query_incidents`` / ``query_inventory``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable

from .contracts import (
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
    InventoryItem,
    InventoryLookupInput,
    InventoryLookupOutput,
)
from .execution import ToolTimeout, call_with_timeout
from .mcp_auth import MCPAuthError, MCPSettings, MCPTokenProvider

logger = logging.getLogger(__name__)

INCIDENT_TOOL_NAME = "incident_lookup"
INVENTORY_TOOL_NAME = "inventory_lookup"

MCP_INCIDENT_TOOL = "query_incidents"
MCP_INVENTORY_TOOL = "query_inventory"

DEFAULT_MCP_TIMEOUT_ENV = "AGENT_MCP_TIMEOUT_SECONDS"


class MCPToolError(RuntimeError):
    """Fallo controlado al invocar una tool MCP."""

    def __init__(self, message: str, *, code: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code


class MCPToolClient:
    """Carga e invoca tools MCP; inyectable en tests mediante ``invoker``."""

    def __init__(
        self,
        settings: MCPSettings | None = None,
        *,
        token_provider: MCPTokenProvider | None = None,
        invoker: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> None:
        self.settings = settings or MCPSettings.from_env()
        self.token_provider = token_provider or MCPTokenProvider(self.settings)
        self._invoker = invoker

    async def _adapter_invoke(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        # Import perezoso: permite tests con invoker inyectado sin la dependencia.
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools

        token = await self.token_provider.get_token()
        client = MultiServerMCPClient(
            {
                "trackflow": {
                    "transport": "streamable_http",
                    "url": self.settings.server_url,
                    "headers": {"Authorization": f"Bearer {token}"},
                    "timeout": self.settings.timeout_seconds,
                    "sse_read_timeout": self.settings.timeout_seconds,
                }
            }
        )
        async with client.session("trackflow") as session:
            tools = await load_mcp_tools(session, handle_tool_errors=False)
            tool = next(
                (candidate for candidate in tools if candidate.name == tool_name),
                None,
            )
            if tool is None:
                raise MCPToolError(
                    f"El servidor MCP no expone la tool '{tool_name}'.",
                    code="unavailable",
                )
            return await tool.ainvoke(arguments)

    async def _invoke_with_retry(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        invoke = self._invoker or self._adapter_invoke
        try:
            return await invoke(tool_name, arguments)
        except Exception as exc:  # noqa: BLE001 - reintento solo si es auth
            if _is_unauthorized(exc) and not self.settings.static_token:
                logger.warning(
                    "Token MCP rechazado; se refresca y se reintenta una vez."
                )
                self.token_provider.invalidate()
                return await invoke(tool_name, arguments)
            raise

    def _run(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Ejecuta el cliente asíncrono desde el grafo síncrono (thread aparte)."""
        return asyncio.run(self._invoke_with_retry(tool_name, arguments))

    def lookup_incident(
        self, payload: IncidentLookupInput
    ) -> IncidentLookupOutput:
        arguments: dict[str, Any] = {"limit": payload.limit}
        if payload.ticket_id is not None:
            arguments["incident_id"] = str(payload.ticket_id)
        else:
            arguments.update(
                {
                    "status": payload.status,
                    "category": payload.category,
                    "origin": payload.origin,
                    "branch": payload.branch,
                }
            )

        try:
            raw = self._run(MCP_INCIDENT_TOOL, _clean(arguments))
        except Exception as exc:  # noqa: BLE001 - fallback controlado
            return _incident_failure(exc)

        try:
            data = _extract_payload(raw)
        except Exception:  # noqa: BLE001
            logger.exception("Respuesta MCP no interpretable (incidencias)")
            return IncidentLookupOutput(
                ok=False,
                found=False,
                error="unavailable",
                message="El servidor MCP devolvió una respuesta no interpretable.",
            )

        incidents = [
            IncidentRecord.model_validate(item)
            for item in (data.get("incidents") or [])
        ]
        if not data.get("found") or not incidents:
            return IncidentLookupOutput(
                ok=False,
                found=False,
                error="not_found",
                message=data.get("message")
                or "No hay incidencias que coincidan con la consulta.",
            )
        return IncidentLookupOutput(
            ok=True, found=True, incidents=incidents
        )

    def lookup_inventory(
        self, payload: InventoryLookupInput
    ) -> InventoryLookupOutput:
        arguments = _clean(
            {
                "sku_id": payload.sku_id,
                "sku_code": payload.sku_code,
                "name_query": payload.name_query,
                "warehouse": payload.warehouse,
                "limit": payload.limit,
            }
        )
        try:
            raw = self._run(MCP_INVENTORY_TOOL, arguments)
        except Exception as exc:  # noqa: BLE001 - fallback controlado
            return _inventory_failure(exc)

        try:
            data = _extract_payload(raw)
        except Exception:  # noqa: BLE001
            logger.exception("Respuesta MCP no interpretable (inventario)")
            return InventoryLookupOutput(
                ok=False,
                found=False,
                error="unavailable",
                message="El servidor MCP devolvió una respuesta no interpretable.",
            )

        items = [
            InventoryItem.model_validate(item)
            for item in (data.get("items") or [])
        ]
        if not data.get("found") or not items:
            return InventoryLookupOutput(
                ok=False,
                found=False,
                error="not_found",
                message=data.get("message")
                or "No hay productos que coincidan con la consulta.",
            )
        return InventoryLookupOutput(ok=True, found=True, items=items)


def _clean(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if value is not None}


def _is_unauthorized(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 401:
        return True
    text = str(exc).lower()
    return "401" in text or "invalid_token" in text or "unauthorized" in text


def _parse_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    while start != -1:
        try:
            candidate = json.loads(text[start:])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(candidate, dict):
            return candidate
        start = text.find("{", start + 1)
    return None


def _extract_payload(raw: Any) -> dict[str, Any]:
    """Extrae el ``structuredContent`` de la respuesta del adaptador."""
    if isinstance(raw, tuple) and len(raw) == 2:
        content, artifact = raw
        if isinstance(artifact, dict):
            if isinstance(artifact.get("structured_content"), dict):
                return artifact["structured_content"]
            if isinstance(artifact.get("structuredContent"), dict):
                return artifact["structuredContent"]
        return _extract_payload(content)

    artifact = getattr(raw, "artifact", None)
    if isinstance(artifact, dict):
        if isinstance(artifact.get("structured_content"), dict):
            return artifact["structured_content"]
        if isinstance(artifact.get("structuredContent"), dict):
            return artifact["structuredContent"]

    content = getattr(raw, "content", raw)

    if isinstance(content, dict):
        if isinstance(content.get("structuredContent"), dict):
            return content["structuredContent"]
        if isinstance(content.get("structured_content"), dict):
            return content["structured_content"]
        if "content" in content:
            return _extract_payload(content["content"])
        return content

    if isinstance(content, str):
        parsed = _parse_json_object(content)
        if parsed is None:
            raise ValueError("La respuesta MCP no contiene JSON.")
        return parsed

    if isinstance(content, list):
        texts = [
            block.get("text")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        for text in texts:
            parsed = _parse_json_object(str(text))
            if parsed is not None:
                return parsed
        if texts:
            return {"message": "\n".join(str(text) for text in texts)}
        raise ValueError("La respuesta MCP no contiene bloques de texto.")

    raise ValueError("La respuesta MCP no es interpretable.")


def _failure_from_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ToolTimeout):
        return "timeout", "El servidor MCP no respondió a tiempo."
    if isinstance(exc, MCPAuthError):
        logger.warning("No se pudo obtener token para el MCP: %s", exc)
        return "unavailable", "No se pudo autenticar contra el servidor MCP."
    if isinstance(exc, MCPToolError):
        return exc.code, str(exc)

    text = str(exc)
    payload = _parse_json_object(text)
    if payload:
        code = str(payload.get("error_code") or "")
        message = str(payload.get("message") or text)
        mapping = {
            "NOT_FOUND": "not_found",
            "INSUFFICIENT_SCOPE": "forbidden",
            "VALIDATION_ERROR": "invalid_input",
            "INVALID_STATUS_TRANSITION": "invalid_input",
            "INVENTORY_READ_ONLY": "forbidden",
            "BACKEND_TIMEOUT": "timeout",
        }
        return mapping.get(code, "unavailable"), message

    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "timeout", "El servidor MCP no respondió a tiempo."
    return "unavailable", "No se pudo consultar el servidor MCP."


def _incident_failure(exc: Exception) -> IncidentLookupOutput:
    code, message = _failure_from_exception(exc)
    logger.warning("Tool MCP de incidencias falló (%s): %s", code, message)
    return IncidentLookupOutput(
        ok=False, found=False, error=code, message=message
    )


def _inventory_failure(exc: Exception) -> InventoryLookupOutput:
    code, message = _failure_from_exception(exc)
    logger.warning("Tool MCP de inventario falló (%s): %s", code, message)
    return InventoryLookupOutput(
        ok=False, found=False, error=code, message=message
    )


def mcp_timeout_seconds() -> float:
    raw = os.getenv(DEFAULT_MCP_TIMEOUT_ENV)
    if raw is None or not str(raw).strip():
        return MCPSettings.from_env().timeout_seconds
    try:
        value = float(raw)
    except ValueError:
        return MCPSettings.from_env().timeout_seconds
    return value if value > 0 else MCPSettings.from_env().timeout_seconds


_client: MCPToolClient | None = None


def get_mcp_client() -> MCPToolClient:
    global _client
    if _client is None:
        _client = MCPToolClient()
    return _client


def set_mcp_client_for_tests(client: MCPToolClient | None) -> None:
    global _client
    _client = client


def lookup_incident(
    payload: IncidentLookupInput | dict,
    *,
    timeout_seconds: float | None = None,
) -> IncidentLookupOutput:
    """Consulta tickets vía MCP con timeout y fallback tipado."""
    if not isinstance(payload, IncidentLookupInput):
        try:
            payload = IncidentLookupInput.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            return IncidentLookupOutput(
                ok=False,
                found=False,
                error="invalid_input",
                message=_validation_message(exc),
            )

    timeout = timeout_seconds or mcp_timeout_seconds()
    try:
        return call_with_timeout(
            lambda: get_mcp_client().lookup_incident(payload), timeout
        )
    except ToolTimeout:
        logger.warning("Timeout consultando incidencias vía MCP tras %ss", timeout)
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="timeout",
            message="El servidor MCP no respondió a tiempo.",
        )
    except Exception:  # noqa: BLE001 - nunca rompe el grafo
        logger.exception("Fallo no controlado en la tool MCP de incidencias")
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="unavailable",
            message="No se pudo consultar el gestor de incidencias.",
        )


def lookup_inventory(
    payload: InventoryLookupInput | dict,
    *,
    timeout_seconds: float | None = None,
) -> InventoryLookupOutput:
    """Consulta stock vía MCP con timeout y fallback tipado."""
    if not isinstance(payload, InventoryLookupInput):
        try:
            payload = InventoryLookupInput.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            return InventoryLookupOutput(
                ok=False,
                found=False,
                error="invalid_input",
                message=_validation_message(exc),
            )

    timeout = timeout_seconds or mcp_timeout_seconds()
    try:
        return call_with_timeout(
            lambda: get_mcp_client().lookup_inventory(payload), timeout
        )
    except ToolTimeout:
        logger.warning("Timeout consultando inventario vía MCP tras %ss", timeout)
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="timeout",
            message="El servidor MCP no respondió a tiempo.",
        )
    except Exception:  # noqa: BLE001 - nunca rompe el grafo
        logger.exception("Fallo no controlado en la tool MCP de inventario")
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="unavailable",
            message="No se pudo consultar el inventario.",
        )


def _validation_message(exc: Exception) -> str:
    errors = getattr(exc, "errors", lambda: [])()
    if errors:
        return str(errors[0].get("msg") or "Entrada inválida.").removeprefix(
            "Value error, "
        )
    return "Entrada inválida."


__all__ = [
    "INCIDENT_TOOL_NAME",
    "INVENTORY_TOOL_NAME",
    "MCP_INCIDENT_TOOL",
    "MCP_INVENTORY_TOOL",
    "MCPToolClient",
    "MCPToolError",
    "get_mcp_client",
    "lookup_incident",
    "lookup_inventory",
    "mcp_timeout_seconds",
    "set_mcp_client_for_tests",
]

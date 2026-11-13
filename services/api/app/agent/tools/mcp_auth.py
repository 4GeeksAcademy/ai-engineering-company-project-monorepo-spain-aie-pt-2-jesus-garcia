"""OAuth client credentials para que el agente llame al MCP Server.

El agente no comparte el JWT local de TrackFlow con el MCP: obtiene un access
token OAuth 2.1 del proveedor (Auth0 u otro) con el grant configurado y lo
presenta como bearer. El token se cachea hasta poco antes de su expiración y se
refresca una vez si el MCP responde 401.

Si el proveedor no está configurado o no responde, el cliente MCP devuelve un
fallback honesto al grafo; nunca rompe la corrida del agente.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_MCP_SERVER_URL = "http://localhost:8001/mcp"
DEFAULT_MCP_TIMEOUT_SECONDS = 10.0
DEFAULT_TOKEN_TIMEOUT_SECONDS = 5.0


class MCPAuthError(RuntimeError):
    """No se pudo obtener un access token para el MCP Server."""


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", " ").split() if item.strip()]


@dataclass(frozen=True)
class MCPSettings:
    server_url: str = DEFAULT_MCP_SERVER_URL
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    audience: str = ""
    resource: str = ""
    scopes: list[str] = field(default_factory=list)
    static_token: str = ""
    grant_type: str = "client_credentials"
    refresh_token: str = ""
    timeout_seconds: float = DEFAULT_MCP_TIMEOUT_SECONDS
    token_timeout_seconds: float = DEFAULT_TOKEN_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        if self.static_token:
            return True
        return bool(self.token_url and self.client_id and self.client_secret)

    @classmethod
    def from_env(cls) -> "MCPSettings":
        def raw(name: str, default: str = "") -> str:
            return (os.getenv(name) or default).strip()

        def number(name: str, default: float) -> float:
            value = raw(name)
            if not value:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        return cls(
            server_url=raw("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL),
            token_url=raw("MCP_OAUTH_TOKEN_URL"),
            client_id=raw("MCP_OAUTH_CLIENT_ID"),
            client_secret=raw("MCP_OAUTH_CLIENT_SECRET"),
            audience=raw("MCP_OAUTH_AUDIENCE"),
            resource=raw("MCP_OAUTH_RESOURCE"),
            scopes=_csv(raw("MCP_OAUTH_SCOPES", "mcp:read")),
            static_token=raw("MCP_AGENT_BEARER_TOKEN"),
            grant_type=raw("MCP_OAUTH_GRANT_TYPE", "client_credentials"),
            refresh_token=raw("MCP_OAUTH_REFRESH_TOKEN"),
            timeout_seconds=number(
                "AGENT_MCP_TIMEOUT_SECONDS", DEFAULT_MCP_TIMEOUT_SECONDS
            ),
            token_timeout_seconds=number(
                "MCP_OAUTH_TIMEOUT_SECONDS", DEFAULT_TOKEN_TIMEOUT_SECONDS
            ),
        )


class MCPTokenProvider:
    """Cache de access tokens OAuth para el cliente MCP."""

    def __init__(
        self,
        settings: MCPSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._token = settings.static_token
        self._expires_at = 0.0

    async def get_token(self, *, force_refresh: bool = False) -> str:
        settings = self.settings
        if settings.static_token and not force_refresh:
            return settings.static_token
        if (
            not force_refresh
            and self._token
            and time.time() < self._expires_at
        ):
            return self._token
        if not settings.configured:
            raise MCPAuthError(
                "El cliente MCP no tiene credenciales OAuth configuradas "
                "(MCP_OAUTH_TOKEN_URL / MCP_OAUTH_CLIENT_ID / "
                "MCP_OAUTH_CLIENT_SECRET o MCP_AGENT_BEARER_TOKEN)."
            )

        data: dict[str, Any] = {
            "grant_type": settings.grant_type,
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
        }
        if settings.audience:
            data["audience"] = settings.audience
        if settings.resource:
            data["resource"] = settings.resource
        if settings.scopes:
            data["scope"] = " ".join(settings.scopes)
        if settings.grant_type == "refresh_token":
            data["refresh_token"] = settings.refresh_token

        try:
            async with httpx.AsyncClient(
                timeout=settings.token_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(settings.token_url, data=data)
        except httpx.TimeoutException as exc:
            raise MCPAuthError(
                "El proveedor OAuth no respondió al solicitar el token MCP."
            ) from exc
        except httpx.RequestError as exc:
            raise MCPAuthError(
                "No se pudo conectar con el proveedor OAuth para el token MCP."
            ) from exc

        if response.status_code >= 400:
            detail = response.text[:300]
            raise MCPAuthError(
                "El proveedor OAuth rechazó la petición de token "
                f"(HTTP {response.status_code}): {detail}"
            )

        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise MCPAuthError(
                "El proveedor OAuth no devolvió un access_token."
            )
        expires_in = payload.get("expires_in")
        try:
            ttl = float(expires_in) if expires_in is not None else 300.0
        except (TypeError, ValueError):
            ttl = 300.0
        self._token = token
        self._expires_at = time.time() + max(ttl - 60.0, 30.0)
        return token

    def invalidate(self) -> None:
        if not self.settings.static_token:
            self._token = ""
            self._expires_at = 0.0


__all__ = [
    "DEFAULT_MCP_SERVER_URL",
    "DEFAULT_MCP_TIMEOUT_SECONDS",
    "MCPAuthError",
    "MCPSettings",
    "MCPTokenProvider",
]

"""Autenticación OAuth del servidor MCP con ``mcpauth`` (modo resource server).

El servidor **no** emite tokens ni implementa un authorization server: valida
JWTs bearer contra el proveedor OIDC configurado (Auth0) y publica el Protected
Resource Metadata (RFC 9728) para que los clientes MCP descubran el issuer.

El scope base se exige en el middleware. Los scopes finos (``mcp:read`` /
``mcp:write``) se comprueban en cada tool para no dar acceso de escritura a un
cliente que solo necesita lectura.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from mcpauth import MCPAuth
from mcpauth.config import AuthServerConfig, AuthServerType
from mcpauth.types import (
    AuthInfo,
    ResourceServerConfig,
    ResourceServerMetadata,
    VerifyAccessTokenFunction,
)
from mcpauth.utils import fetch_server_config
from starlette.middleware import Middleware

from .settings import Settings

logger = logging.getLogger(__name__)

_mcp_auth: MCPAuth | None = None
_settings: Settings | None = None
_verify_override: VerifyAccessTokenFunction | None = None


class AuthConfigurationError(RuntimeError):
    """No se pudo configurar el resource server o su issuer OIDC."""


def configure_auth(
    settings: Settings,
    *,
    auth_server_config: AuthServerConfig | None = None,
    verify_override: VerifyAccessTokenFunction | None = None,
) -> MCPAuth:
    """Crea el ``MCPAuth`` en modo resource server y lo deja como singleton."""
    global _mcp_auth, _settings, _verify_override

    if auth_server_config is None:
        try:
            auth_server_config = fetch_server_config(
                settings.auth_issuer,
                AuthServerType(settings.auth_type),
            )
        except Exception as exc:  # noqa: BLE001 - se convierte en arranque fallido
            raise AuthConfigurationError(
                "No se pudo obtener la metadata OIDC del issuer "
                f"{settings.auth_issuer!r}: {exc}"
            ) from exc

    mcp_auth = MCPAuth(
        protected_resources=[
            ResourceServerConfig(
                metadata=ResourceServerMetadata(
                    resource=settings.resource_url,
                    authorization_servers=[auth_server_config],
                    scopes_supported=settings.scopes_supported,
                    resource_name="TrackFlow Operations MCP",
                    resource_documentation=(
                        "https://github.com/4GeeksAcademy/"
                        "ai-engineering-company-project-monorepo-spain-aie-pt-2-jesus-garcia"
                    ),
                    bearer_methods_supported=["header"],
                )
            )
        ]
    )

    _mcp_auth = mcp_auth
    _settings = settings
    _verify_override = verify_override
    logger.info(
        "MCP Auth configurado (resource=%s, issuer=%s, scopes=%s)",
        settings.resource_url,
        settings.auth_issuer,
        ",".join(settings.scopes_supported),
    )
    return mcp_auth


def get_auth() -> MCPAuth:
    if _mcp_auth is None:
        raise AuthConfigurationError(
            "MCPAuth no está configurado. Llama a configure_auth() al arrancar."
        )
    return _mcp_auth


def get_settings() -> Settings:
    if _settings is None:
        raise AuthConfigurationError("Settings no están configurados.")
    return _settings


def current_auth() -> AuthInfo | None:
    """``AuthInfo`` del request actual (lo rellena el middleware de mcpauth)."""
    if _mcp_auth is None:
        return None
    return _mcp_auth.auth_info


def resource_metadata_routes() -> list[Any]:
    """Rutas públicas del Protected Resource Metadata."""
    return list(get_auth().resource_metadata_router().routes)


def bearer_middleware() -> Middleware:
    """Middleware bearer para montar únicamente sobre la app MCP."""
    settings = get_settings()
    mcp_auth = get_auth()
    mode: Any = _verify_override or "jwt"
    return Middleware(
        mcp_auth.bearer_auth_middleware(
            mode,
            audience=settings.resource_url,
            required_scopes=[settings.base_scope],
            resource=settings.resource_url,
            show_error_details=settings.show_error_details,
        )
    )


def require_scope(
    scope: str,
    *,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> AuthInfo:
    """Comprueba el scope fino de una tool y devuelve el ``AuthInfo``."""
    from .errors import ErrorCode, ToolFailure

    auth_info = current_auth()
    if auth_info is None:
        raise ToolFailure(
            ErrorCode.INSUFFICIENT_SCOPE,
            "La petición no tiene información de autenticación válida.",
            details={"required_scope": scope},
        )

    granted = set(auth_info.scopes or [])
    if scope not in granted:
        raise ToolFailure(
            ErrorCode.INSUFFICIENT_SCOPE,
            f"El token no tiene el scope requerido '{scope}'.",
            details={
                "required_scope": scope,
                "granted_scopes": sorted(granted),
            },
        )
    return auth_info


def set_auth_info_for_tests(auth_info: AuthInfo | None) -> None:
    """Inyecta un ``AuthInfo`` en el ContextVar de mcpauth (solo tests)."""
    if _mcp_auth is None:
        raise AuthConfigurationError("MCPAuth no está configurado.")
    _mcp_auth._context_var.set(auth_info)  # noqa: SLF001 - helper de test


def reset_for_tests() -> None:
    global _mcp_auth, _settings, _verify_override
    _mcp_auth = None
    _settings = None
    _verify_override = None


__all__ = [
    "AuthConfigurationError",
    "bearer_middleware",
    "configure_auth",
    "current_auth",
    "get_auth",
    "get_settings",
    "require_scope",
    "reset_for_tests",
    "resource_metadata_routes",
    "set_auth_info_for_tests",
]

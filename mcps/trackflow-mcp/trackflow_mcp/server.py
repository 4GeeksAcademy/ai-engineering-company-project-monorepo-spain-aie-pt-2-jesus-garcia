"""Composición del servidor MCP: FastMCP + mcpauth + Starlette.

El endpoint MCP vive en ``/mcp``. El Protected Resource Metadata es público y
se publica en la ruta derivada del resource identifier (``.../mcp`` →
``/.well-known/oauth-protected-resource/mcp``). Todo lo demás pasa por el
middleware bearer de ``mcpauth``.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import (
    bearer_middleware,
    configure_auth,
    get_settings,
    resource_metadata_routes,
)
from .backend import close_api, configure_api
from .logs import configure_logging
from .settings import Settings, load_settings
from .tools.incidents import register_incident_tools
from .tools.inventory import register_inventory_tools

logger = logging.getLogger(__name__)


def _build_fastmcp(settings: Settings) -> FastMCP:
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=(
            not settings.disable_dns_rebinding_protection
        ),
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )
    return FastMCP(
        name=settings.service_name,
        instructions=(
            "TrackFlow Operations MCP. Expone datos operativos en tiempo real "
            "del gestor de incidencias y del inventario. Usa query_incidents "
            "para tickets, get_incident_summary para métricas, create_incident "
            "y update_incident_status para el ciclo de vida, y query_inventory "
            "para stock. El inventario es de solo lectura: adjust_inventory_stock "
            "siempre rechaza la escritura con INVENTORY_READ_ONLY."
        ),
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=False,
        transport_security=security,
    )


async def health(_: Request) -> JSONResponse:
    """Healthcheck público; no expone datos de la compañía."""
    return JSONResponse({"status": "ok", "service": "trackflow-mcp"})


async def not_found(_: Request) -> JSONResponse:
    """404 explícito para rutas de discovery no canónicas."""
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def create_app(
    settings: Settings | None = None,
    *,
    auth_server_config: Any | None = None,
    verify_override: Any | None = None,
) -> Starlette:
    """Crea la app ASGI. Inyectable en tests (issuer/verify de prueba)."""
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.log_format)
    configure_auth(
        settings,
        auth_server_config=auth_server_config,
        verify_override=verify_override,
    )
    configure_api(settings)

    mcp = _build_fastmcp(settings)
    register_incident_tools(mcp)
    register_inventory_tools(mcp)
    mcp_http_app = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # El session manager de Streamable HTTP debe arrancar con la app padre.
        async with mcp_http_app.router.lifespan_context(mcp_http_app):
            try:
                yield
            finally:
                await close_api()

    routes = [
        *resource_metadata_routes(),
        Route("/health", health, methods=["GET"]),
        # Rutas de discovery que algunos clientes prueban en la raíz: 404
        # explícito en lugar de un 401 del bearer, para no confundir el
        # descubrimiento. La ruta canónica es .../oauth-protected-resource/mcp.
        Route(
            "/.well-known/oauth-protected-resource",
            not_found,
            methods=["GET"],
        ),
        Route(
            "/.well-known/oauth-authorization-server",
            not_found,
            methods=["GET"],
        ),
        Route(
            "/.well-known/openid-configuration",
            not_found,
            methods=["GET"],
        ),
        Mount(
            "/",
            app=mcp_http_app,
            middleware=[bearer_middleware()],
        ),
    ]

    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors_origins,
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
            )
        ],
    )


def __getattr__(name: str) -> Any:
    """Crea ``app`` de forma perezosa para no romper imports en tests."""
    if name == "app":
        app = create_app()
        globals()["app"] = app
        return app
    raise AttributeError(name)


__all__ = ["create_app", "get_settings"]

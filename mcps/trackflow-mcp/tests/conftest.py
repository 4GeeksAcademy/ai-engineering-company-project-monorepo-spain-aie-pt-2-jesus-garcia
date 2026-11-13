"""Fixtures de test del MCP Server.

No se usa red ni Auth0: se inyecta un ``AuthServerConfig`` de prueba y un
verificador de tokens que reconoce ``read`` / ``write``. La API de TrackFlow se
sustituye por un doble en memoria.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["MCP_RESOURCE_URL"] = "https://mcp.test/mcp"
os.environ["MCP_AUTH_ISSUER"] = "https://issuer.test/"
os.environ["MCP_AUTH_TYPE"] = "oidc"
os.environ["MCP_BASE_SCOPE"] = "mcp:read"
os.environ["MCP_SCOPES_SUPPORTED"] = "mcp:read,mcp:write"
os.environ["TRACKFLOW_API_BASE_URL"] = "http://api.test"
os.environ["TRACKFLOW_API_EMAIL"] = "service@test.com"
os.environ["TRACKFLOW_API_PASSWORD"] = "secret"
os.environ["MCP_DISABLE_DNS_REBINDING_PROTECTION"] = "true"
os.environ["MCP_LOG_LEVEL"] = "INFO"
os.environ["MCP_LOG_FORMAT"] = "json"

from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from mcpauth.config import (  # noqa: E402
    AuthServerConfig,
    AuthServerType,
    AuthorizationServerMetadata,
)
from mcpauth.exceptions import (  # noqa: E402
    MCPAuthTokenVerificationException,
    MCPAuthTokenVerificationExceptionCode,
)
from mcpauth.types import AuthInfo  # noqa: E402

from trackflow_mcp import auth, backend  # noqa: E402
from trackflow_mcp.server import create_app  # noqa: E402
from trackflow_mcp.settings import Settings, load_settings  # noqa: E402


@pytest.fixture()
def settings() -> Settings:
    return dataclasses.replace(
        load_settings(), disable_dns_rebinding_protection=True
    )


@pytest.fixture()
def auth_server_config(settings: Settings) -> AuthServerConfig:
    issuer = settings.auth_issuer
    return AuthServerConfig(
        metadata=AuthorizationServerMetadata(
            issuer=issuer,
            authorization_endpoint=issuer + "authorize",
            token_endpoint=issuer + "oauth/token",
            jwks_uri=issuer + ".well-known/jwks.json",
            response_types_supported=["code"],
            grant_types_supported=["authorization_code", "refresh_token"],
            code_challenge_methods_supported=["S256"],
        ),
        type=AuthServerType.OIDC,
    )


def make_auth_info(
    token: str,
    *,
    scopes: list[str],
    issuer: str = "https://issuer.test/",
    audience: str = "https://mcp.test/mcp",
) -> AuthInfo:
    return AuthInfo(
        token=token,
        issuer=issuer,
        client_id="test-client",
        subject="user-1",
        scopes=scopes,
        audience=audience,
        claims={"aud": audience, "scope": " ".join(scopes)},
    )


@pytest.fixture()
def verify_override(settings: Settings):
    def verify(token: str) -> AuthInfo:
        if token == "read":
            return make_auth_info(token, scopes=["mcp:read"])
        if token == "write":
            return make_auth_info(token, scopes=["mcp:read", "mcp:write"])
        if token == "noscope":
            return make_auth_info(token, scopes=["mcp:write"])
        raise MCPAuthTokenVerificationException(
            MCPAuthTokenVerificationExceptionCode.INVALID_TOKEN,
            cause={"error_description": "token rejected"},
        )

    return verify


class FakeAPI:
    """Doble del cliente HTTP; registra llamadas y devuelve datos fijos."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.handlers: dict[tuple[str, str], Any] = {}

    def on(self, method: str, path: str, response: Any) -> "FakeAPI":
        self.handlers[(method.upper(), path)] = response
        return self

    async def _call(
        self, method: str, path: str, params=None, json=None, **_: Any
    ) -> Any:
        self.calls.append(
            {"method": method, "path": path, "params": params, "json": json}
        )
        handler = self.handlers.get((method.upper(), path))
        if handler is None:
            raise AssertionError(f"Llamada inesperada: {method} {path}")
        if isinstance(handler, Exception):
            raise handler
        if callable(handler):
            return handler(params=params, json=json)
        return handler

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._call("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self._call("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self._call("PATCH", path, **kwargs)

    async def close(self) -> None:
        return None


@pytest.fixture()
def fake_api() -> FakeAPI:
    return FakeAPI()


@pytest.fixture()
async def app(settings, auth_server_config, verify_override, fake_api):
    application = create_app(
        settings,
        auth_server_config=auth_server_config,
        verify_override=verify_override,
    )
    backend.set_api_for_tests(fake_api)
    async with LifespanManager(application):
        yield application
    auth.reset_for_tests()
    backend.reset_api_for_tests()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture()
def read_auth(app):
    auth.set_auth_info_for_tests(
        make_auth_info("read", scopes=["mcp:read"])
    )
    yield
    auth.set_auth_info_for_tests(None)


@pytest.fixture()
def write_auth(app):
    auth.set_auth_info_for_tests(
        make_auth_info("write", scopes=["mcp:read", "mcp:write"])
    )
    yield
    auth.set_auth_info_for_tests(None)

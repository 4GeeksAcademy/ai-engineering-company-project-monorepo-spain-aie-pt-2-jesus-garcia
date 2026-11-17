#!/usr/bin/env python3
"""Servidor MCP de desarrollo con un verificador de tokens local.

SOLO PARA DESARROLLO/VALIDACIÓN LOCAL. No usa Auth0 ni valida firmas: acepta
``test-read`` y ``test-write``. Sirve para probar el flujo HTTP completo
(``scripts/mcp_smoke.py`` + API real) sin depender de un proveedor OAuth.

En producción se arranca ``uvicorn trackflow_mcp.server:app`` con Auth0.

    python scripts/local_test_server.py            # :8010
    python scripts/mcp_smoke.py \
      --url http://127.0.0.1:8010/mcp --token test-write --write
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402
from mcpauth.config import (
    AuthServerConfig,
    AuthServerType,
    AuthorizationServerMetadata,
)
from mcpauth.exceptions import (
    MCPAuthTokenVerificationException,
    MCPAuthTokenVerificationExceptionCode,
)
from mcpauth.types import AuthInfo

from trackflow_mcp.server import create_app
from trackflow_mcp.settings import load_settings


def build_test_app():
    settings = load_settings()
    metadata = AuthorizationServerMetadata(
        issuer=settings.auth_issuer,
        authorization_endpoint=settings.auth_issuer + "authorize",
        token_endpoint=settings.auth_issuer + "oauth/token",
        jwks_uri=settings.auth_issuer + ".well-known/jwks.json",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code"],
        code_challenge_methods_supported=["S256"],
    )
    auth_server_config = AuthServerConfig(
        metadata=metadata, type=AuthServerType.OIDC
    )

    def verify(token: str) -> AuthInfo:
        if token == "test-read":
            scopes = ["mcp:read"]
        elif token == "test-write":
            scopes = ["mcp:read", "mcp:write"]
        else:
            raise MCPAuthTokenVerificationException(
                MCPAuthTokenVerificationExceptionCode.INVALID_TOKEN
            )
        return AuthInfo(
            token=token,
            issuer=settings.auth_issuer,
            client_id="local-test-client",
            subject="local-tester",
            scopes=scopes,
            audience=settings.resource_url,
            claims={"aud": settings.resource_url},
        )

    return create_app(
        settings,
        auth_server_config=auth_server_config,
        verify_override=verify,
    )


if __name__ == "__main__":
    uvicorn.run(build_test_app(), host="127.0.0.1", port=8010)

"""Tests del cliente HTTP contra la API de TrackFlow."""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from trackflow_mcp.backend import TrackFlowAPI
from trackflow_mcp.errors import BackendError, ErrorCode


def make_api(handler, *, token: str = "static-token") -> TrackFlowAPI:
    from trackflow_mcp.settings import load_settings

    settings = dataclasses.replace(
        load_settings(),
        api_token=token,
        api_email="service@test.com",
        api_password="secret",
        api_timeout_seconds=1,
    )
    return TrackFlowAPI(
        settings, transport=httpx.MockTransport(handler)
    )


async def test_static_token_is_sent():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    api = make_api(handler)
    try:
        result = await api.get("/inventory/products")
    finally:
        await api.close()
    assert result == []
    assert seen[0].headers["authorization"] == "Bearer static-token"


async def test_login_is_cached_and_refreshed_on_401():
    calls: list[httpx.Request] = []
    logins = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/auth/login":
            logins["count"] += 1
            return httpx.Response(
                200, json={"access_token": f"token-{logins['count']}"}
            )
        if request.url.path == "/inventory/products":
            if logins["count"] == 1:
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json=[{"id": 1}])
        raise AssertionError(request.url)

    api = make_api(handler, token="")
    try:
        result = await api.get("/inventory/products")
        await api.get("/inventory/products")
    finally:
        await api.close()

    assert result == [{"id": 1}]
    assert logins["count"] == 2
    auth_headers = [
        call.headers["authorization"]
        for call in calls
        if call.url.path == "/inventory/products"
    ]
    assert auth_headers[0] == "Bearer token-1"
    assert auth_headers[1] == "Bearer token-2"


@pytest.mark.parametrize(
    ("status", "path", "expected"),
    [
        (404, "/api/incidents/999", ErrorCode.NOT_FOUND),
        (400, "/api/incidents/42/status", ErrorCode.INVALID_STATUS_TRANSITION),
        (400, "/api/incidents", ErrorCode.VALIDATION_ERROR),
        (422, "/api/incidents", ErrorCode.VALIDATION_ERROR),
        (401, "/inventory/products", ErrorCode.BACKEND_AUTH_FAILED),
        (403, "/inventory/products", ErrorCode.BACKEND_AUTH_FAILED),
        (500, "/inventory/products", ErrorCode.BACKEND_UNAVAILABLE),
    ],
)
async def test_http_errors_are_mapped(status, path, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "detalle del backend"})

    api = make_api(handler)
    try:
        with pytest.raises(BackendError) as exc:
            await api.get(path)
    finally:
        await api.close()
    assert exc.value.code == expected
    assert "detalle del backend" in exc.value.message


async def test_timeout_is_mapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    api = make_api(handler)
    try:
        with pytest.raises(BackendError) as exc:
            await api.get("/inventory/products")
    finally:
        await api.close()
    assert exc.value.code == ErrorCode.BACKEND_TIMEOUT


async def test_connection_error_is_mapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    api = make_api(handler)
    try:
        with pytest.raises(BackendError) as exc:
            await api.get("/inventory/products")
    finally:
        await api.close()
    assert exc.value.code == ErrorCode.BACKEND_UNAVAILABLE

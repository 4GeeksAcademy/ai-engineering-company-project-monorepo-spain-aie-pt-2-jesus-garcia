"""Cliente HTTP contra la API real de TrackFlow.

El servidor MCP nunca lee TinyDB ni SQLModel directamente: llama a los mismos
endpoints REST que usa el backoffice. Para autenticarse usa una cuenta de
servicio con rol manager (o un token estático) y cachea el JWT, refrescándolo
una vez si la API responde 401.

Los cambios de estado de incidencias pasan exclusivamente por
``PATCH /api/incidents/{id}/status``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .errors import BackendError, ErrorCode
from .settings import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_TTL_SECONDS = 1200.0
_api: "TrackFlowAPI | None" = None


class TrackFlowAPI:
    """Cliente asíncrono mínimo de la API de TrackFlow."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._static_token = settings.api_token.strip()
        self._token = self._static_token
        self._token_expires_at = 0.0
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.api_base_url.rstrip("/"),
            timeout=settings.api_timeout_seconds,
            transport=transport,
        )

    async def __aenter__(self) -> "TrackFlowAPI":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _login(self) -> str:
        if not (self._settings.api_email and self._settings.api_password):
            raise BackendError(
                ErrorCode.BACKEND_AUTH_FAILED,
                "El servidor MCP no tiene credenciales de servicio configuradas.",
                path="/api/auth/login",
            )
        try:
            response = await self._client.post(
                "/api/auth/login",
                json={
                    "email": self._settings.api_email,
                    "password": self._settings.api_password,
                },
            )
        except httpx.TimeoutException as exc:
            raise BackendError(
                ErrorCode.BACKEND_TIMEOUT,
                "La API de TrackFlow no respondió al autenticar el servicio.",
                path="/api/auth/login",
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                ErrorCode.BACKEND_UNAVAILABLE,
                "No se pudo conectar con la API de TrackFlow.",
                path="/api/auth/login",
            ) from exc

        if response.status_code >= 400:
            detail = _extract_detail(response)
            raise BackendError(
                ErrorCode.BACKEND_AUTH_FAILED,
                "La cuenta de servicio del MCP no pudo autenticarse: "
                f"{detail}",
                status_code=response.status_code,
                path="/api/auth/login",
            )
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise BackendError(
                ErrorCode.BACKEND_AUTH_FAILED,
                "La API no devolvió un access token para la cuenta de servicio.",
                status_code=response.status_code,
                path="/api/auth/login",
            )
        self._token = token
        self._token_expires_at = time.time() + _DEFAULT_TOKEN_TTL_SECONDS
        return token

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        if self._static_token and not force_refresh:
            return self._static_token
        if (
            not force_refresh
            and self._token
            and time.time() < self._token_expires_at
        ):
            return self._token
        return await self._login()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._get_token()
        try:
            response = await self._client.request(
                method,
                path,
                params=_clean_params(params),
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException as exc:
            raise BackendError(
                ErrorCode.BACKEND_TIMEOUT,
                "La API de TrackFlow no respondió dentro del tiempo esperado.",
                path=path,
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                ErrorCode.BACKEND_UNAVAILABLE,
                "No se pudo conectar con la API de TrackFlow.",
                path=path,
            ) from exc

        if response.status_code == 401 and not self._static_token:
            # El JWT de servicio puede haber expirado: refrescar una sola vez.
            token = await self._get_token(force_refresh=True)
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=_clean_params(params),
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.TimeoutException as exc:
                raise BackendError(
                    ErrorCode.BACKEND_TIMEOUT,
                    "La API de TrackFlow no respondió dentro del tiempo esperado.",
                    path=path,
                ) from exc
            except httpx.RequestError as exc:
                raise BackendError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    "No se pudo conectar con la API de TrackFlow.",
                    path=path,
                ) from exc

        if response.status_code >= 400:
            raise _map_response(response, path)
        if response.status_code == 204:
            return {}
        return response.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, **kwargs)


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _extract_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
    return str(payload)[:300]


def _map_response(response: httpx.Response, path: str) -> BackendError:
    status = response.status_code
    detail = _extract_detail(response)

    if status == 404:
        return BackendError(
            ErrorCode.NOT_FOUND,
            detail or "El recurso solicitado no existe.",
            status_code=status,
            path=path,
        )
    if status in (401, 403):
        return BackendError(
            ErrorCode.BACKEND_AUTH_FAILED,
            "La API rechazó la petición del servicio MCP: " + detail,
            status_code=status,
            path=path,
        )
    if status == 422:
        return BackendError(
            ErrorCode.VALIDATION_ERROR,
            "La API rechazó los datos enviados: " + detail,
            status_code=status,
            details={"detail": detail},
            path=path,
        )
    if status == 400:
        code = (
            ErrorCode.INVALID_STATUS_TRANSITION
            if path.rstrip("/").endswith("/status")
            else ErrorCode.VALIDATION_ERROR
        )
        return BackendError(
            code,
            detail or "La API rechazó la petición por datos inválidos.",
            status_code=status,
            details={"detail": detail},
            path=path,
        )
    return BackendError(
        ErrorCode.BACKEND_UNAVAILABLE,
        f"La API de TrackFlow respondió HTTP {status}: {detail}",
        status_code=status,
        path=path,
    )


def configure_api(settings: Settings) -> TrackFlowAPI:
    global _api
    _api = TrackFlowAPI(settings)
    return _api


def get_api() -> TrackFlowAPI:
    if _api is None:
        raise RuntimeError(
            "El cliente de la API de TrackFlow no está configurado."
        )
    return _api


def set_api_for_tests(api: Any) -> None:
    global _api
    _api = api


async def close_api() -> None:
    global _api
    if _api is not None:
        await _api.close()
    _api = None


def reset_api_for_tests() -> None:
    global _api
    _api = None


__all__ = [
    "TrackFlowAPI",
    "close_api",
    "configure_api",
    "get_api",
    "reset_api_for_tests",
    "set_api_for_tests",
]

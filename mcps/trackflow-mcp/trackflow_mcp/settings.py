"""Configuración del servidor MCP.

Toda la configuración se lee de variables de entorno (o del `.env` local del
servidor). El arranque falla de forma explícita si falta el issuer OIDC o la URL
pública del recurso: sin esos dos valores no se puede publicar el Protected
Resource Metadata ni validar la audiencia de los tokens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE, override=False)


class SettingsError(RuntimeError):
    """Configuración incompleta o incoherente."""


def _raw(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _csv(name: str, default: str = "") -> list[str]:
    raw = _raw(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool(name: str, default: bool = False) -> bool:
    raw = _raw(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = _raw(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} debe ser numérico.") from exc


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable del servidor."""

    service_name: str
    resource_url: str
    auth_issuer: str
    auth_type: str
    base_scope: str
    scopes_supported: list[str] = field(default_factory=list)
    show_error_details: bool = False

    host: str = "0.0.0.0"
    port: int = 8001
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_origins: list[str] = field(default_factory=list)
    cors_origins: list[str] = field(default_factory=list)
    disable_dns_rebinding_protection: bool = False

    api_base_url: str = "http://localhost:8000"
    api_email: str = ""
    api_password: str = ""
    api_token: str = ""
    api_timeout_seconds: float = 8.0

    log_level: str = "INFO"
    log_format: str = "json"

    def validate(self) -> None:
        if not self.resource_url:
            raise SettingsError("MCP_RESOURCE_URL es obligatoria.")
        if not self.resource_url.startswith(("http://", "https://")):
            raise SettingsError("MCP_RESOURCE_URL debe ser una URL http(s).")
        if not self.auth_issuer:
            raise SettingsError("MCP_AUTH_ISSUER es obligatorio.")
        if not self.auth_issuer.startswith(("http://", "https://")):
            raise SettingsError("MCP_AUTH_ISSUER debe ser una URL http(s).")
        if self.auth_type not in {"oidc", "oauth"}:
            raise SettingsError("MCP_AUTH_TYPE debe ser 'oidc' u 'oauth'.")
        if not self.scopes_supported:
            raise SettingsError("MCP_SCOPES_SUPPORTED no puede estar vacío.")
        if self.base_scope not in self.scopes_supported:
            raise SettingsError(
                "MCP_BASE_SCOPE debe estar incluido en MCP_SCOPES_SUPPORTED."
            )
        if not self.api_base_url:
            raise SettingsError("TRACKFLOW_API_BASE_URL es obligatoria.")
        if not self.api_token and not (self.api_email and self.api_password):
            raise SettingsError(
                "Configura TRACKFLOW_API_TOKEN o TRACKFLOW_API_EMAIL/PASSWORD."
            )

    @property
    def resource_host(self) -> str:
        return urlparse(self.resource_url).hostname or ""

    @property
    def metadata_path(self) -> str:
        """Path del PRM derivado del resource identifier (RFC 9728 §3.1)."""
        parsed = urlparse(self.resource_url)
        path = parsed.path.rstrip("/")
        return f"/.well-known/oauth-protected-resource{path}"


def load_settings() -> Settings:
    defaults_scopes = ["mcp:read", "mcp:write"]
    resource_url = _raw("MCP_RESOURCE_URL").rstrip("/")
    auth_issuer = _raw("MCP_AUTH_ISSUER")
    scopes = _csv("MCP_SCOPES_SUPPORTED", ",".join(defaults_scopes))
    base_scope = _raw("MCP_BASE_SCOPE", "mcp:read")

    allowed_hosts = _csv("MCP_ALLOWED_HOSTS", "localhost,127.0.0.1")
    resource_host = urlparse(resource_url).hostname
    if resource_host and resource_host not in allowed_hosts:
        allowed_hosts.append(resource_host)

    settings = Settings(
        service_name=_raw("MCP_SERVICE_NAME", "trackflow-mcp"),
        resource_url=resource_url,
        auth_issuer=auth_issuer,
        auth_type=_raw("MCP_AUTH_TYPE", "oidc").lower(),
        base_scope=base_scope,
        scopes_supported=scopes,
        show_error_details=_bool("MCP_SHOW_ERROR_DETAILS", False),
        host=_raw("MCP_HOST", "0.0.0.0"),
        port=int(_raw("MCP_PORT", "8001")),
        allowed_hosts=allowed_hosts,
        allowed_origins=_csv("MCP_ALLOWED_ORIGINS"),
        cors_origins=_csv("MCP_CORS_ORIGINS", "*") or ["*"],
        disable_dns_rebinding_protection=_bool(
            "MCP_DISABLE_DNS_REBINDING_PROTECTION", False
        ),
        api_base_url=_raw("TRACKFLOW_API_BASE_URL", "http://localhost:8000"),
        api_email=_raw("TRACKFLOW_API_EMAIL"),
        api_password=_raw("TRACKFLOW_API_PASSWORD"),
        api_token=_raw("TRACKFLOW_API_TOKEN"),
        api_timeout_seconds=_float("TRACKFLOW_API_TIMEOUT_SECONDS", 8.0),
        log_level=_raw("MCP_LOG_LEVEL", "INFO").upper(),
        log_format=_raw("MCP_LOG_FORMAT", "json").lower(),
    )
    settings.validate()
    return settings


__all__ = ["ENV_FILE", "Settings", "SettingsError", "load_settings"]

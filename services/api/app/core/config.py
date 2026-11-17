"""Configuración de seguridad centralizada de TrackFlow.

Este módulo concentra las decisiones que antes estaban dispersas (o
hardcodeadas) en ``main.py`` y ``security.py``:

* entorno de ejecución (``development`` / ``test`` / ``production``);
* validación de ``SECRET_KEY`` y ``ALLOWED_ORIGINS`` al arrancar;
* registro público de usuarios;
* lista blanca de orígenes CORS.

La validación es deliberadamente estricta **solo** en producción para no
romper el flujo de desarrollo ni la suite de tests. En producción el proceso
falla al arrancar si la configuración es insegura (fail fast).
"""

from __future__ import annotations

import os

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,http://localhost:3000,http://localhost:3001"
)

# Secretos de ejemplo/documentación que nunca deben llegar a producción.
WEAK_SECRETS = {
    "",
    "change-this-to-a-random-secret-in-production",
    "change-me",
    "changeme",
    "secret",
    "test-secret-key",
}

MIN_SECRET_LENGTH = 32
MIN_PRODUCTION_PASSWORD_LENGTH = 12


def environment() -> str:
    return (os.getenv("ENVIRONMENT") or "development").strip().lower()


def is_production() -> bool:
    return environment() in {"production", "prod"}


def allowed_origins() -> list[str]:
    """Orígenes CORS permitidos, sin comodines.

    Se lee ``ALLOWED_ORIGINS`` en cada llamada (no al importar) para que los
    tests puedan sobreescribirla y para que el arranque en producción use el
    valor real del entorno.
    """

    raw = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if "*" in origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS no puede contener '*' con credenciales habilitadas."
        )
    return origins


def public_registration_enabled() -> bool:
    """El registro público se desactiva por defecto en producción."""

    raw = os.getenv("ALLOW_PUBLIC_REGISTRATION")
    if raw is None:
        return not is_production()
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def validate_security_config() -> None:
    """Valida la configuración crítica. Falla en producción si es insegura."""

    if not is_production():
        return

    secret = (os.getenv("SECRET_KEY") or "").strip()
    if secret.lower() in WEAK_SECRETS or len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            "SECRET_KEY insegura en producción: define un secreto aleatorio de "
            f"al menos {MIN_SECRET_LENGTH} caracteres "
            "(por ejemplo: openssl rand -base64 48)."
        )

    origins = allowed_origins()
    if not origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS es obligatoria en producción (lista separada por comas)."
        )

    service_password = (os.getenv("TRACKFLOW_API_PASSWORD") or "").strip()
    if service_password and (
        service_password == "admin123"
        or len(service_password) < MIN_PRODUCTION_PASSWORD_LENGTH
    ):
        raise RuntimeError(
            "TRACKFLOW_API_PASSWORD es débil en producción: usa al menos "
            f"{MIN_PRODUCTION_PASSWORD_LENGTH} caracteres y rota la cuenta de servicio."
        )


__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "MIN_PRODUCTION_PASSWORD_LENGTH",
    "MIN_SECRET_LENGTH",
    "allowed_origins",
    "environment",
    "is_production",
    "public_registration_enabled",
    "validate_security_config",
]

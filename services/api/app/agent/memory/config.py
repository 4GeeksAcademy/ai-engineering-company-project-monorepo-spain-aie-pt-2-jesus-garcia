"""Configuración de la memoria del agente.

Los valores se leen del entorno con defaults seguros. No se añaden variables a
``.env.example`` en esta entrega (archivo protegido); la documentación de diseño
las recoge para que el equipo las desplegue cuando quiera.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name) or ""
    return tuple(
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    )


def utcnow() -> datetime:
    """Ahora en UTC (aware)."""

    return datetime.now(timezone.utc)


ENABLED = os.getenv("AGENT_MEMORY_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

#: Caducidad del contexto operativo (huelgas, congestión, retrasos puntuales).
EPISODIC_TTL_DAYS = _int_env("AGENT_MEMORY_EPISODIC_TTL_DAYS", 7)

#: Revisión de una regla de carrier (cobertura, rutas, carrier local).
CARRIER_REVIEW_DAYS = _int_env("AGENT_MEMORY_CARRIER_REVIEW_DAYS", 90)

#: Revisión de una preferencia de cliente B2B.
CLIENT_REVIEW_DAYS = _int_env("AGENT_MEMORY_CLIENT_REVIEW_DAYS", 180)

#: Una propuesta sin respuesta caduca y se rechaza (nunca se aprueba sola).
PROPOSAL_TTL_HOURS = _int_env("AGENT_MEMORY_PROPOSAL_TTL_HOURS", 24)

#: Límites del bloque de memoria que se inyecta en el prompt.
MAX_CONTEXT_ENTRIES = _int_env("AGENT_MEMORY_MAX_CONTEXT_ENTRIES", 12)
MAX_CONTEXT_CHARS = _int_env("AGENT_MEMORY_MAX_CONTEXT_CHARS", 4_000)

#: Tope de entradas activas antes de que la consolidación empiece a expulsar.
MAX_ACTIVE_ENTRIES = _int_env("AGENT_MEMORY_MAX_ACTIVE_ENTRIES", 200)

#: Longitud máxima de un hecho memorizable.
MAX_FACT_CHARS = _int_env("AGENT_MEMORY_MAX_FACT_CHARS", 600)
MAX_REASON_CHARS = _int_env("AGENT_MEMORY_MAX_REASON_CHARS", 300)
MAX_QUOTE_CHARS = _int_env("AGENT_MEMORY_MAX_QUOTE_CHARS", 400)
MAX_ORIGIN_MESSAGE_CHARS = _int_env(
    "AGENT_MEMORY_MAX_ORIGIN_MESSAGE_CHARS", 2_000
)

#: Umbral de confianza del clasificador de intención. Por debajo, rechazo.
INTENT_MIN_CONFIDENCE = _float_env("AGENT_MEMORY_INTENT_MIN_CONFIDENCE", 0.6)

#: Roles que pueden aprobar tipos de memoria que contradicen la política
#: curada. Vacío = cualquier usuario autenticado (flujo del brief).
POLICY_APPROVER_ROLES = set(_csv_env("AGENT_MEMORY_POLICY_APPROVER_ROLES"))
POLICY_MEMORY_TYPES = set(
    _csv_env("AGENT_MEMORY_POLICY_MEMORY_TYPES")
    or ("carrier_rule", "operational_context")
)

MEMORY_TYPES = (
    "carrier_rule",
    "operational_context",
    "client_preference",
)

SCOPE_TYPES = ("carrier", "ops", "client")

PROPOSAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "edited",
    "blocked",
    "expired",
)

ENTRY_STATUSES = (
    "active",
    "superseded",
    "expired",
    "stale",
    "retired",
    "blocked",
)

MEMORY_QUESTION = (
    "¿Quieres que lo recuerde para futuras conversaciones? "
    "Responde «sí» para guardarlo o «no» para descartarlo."
)

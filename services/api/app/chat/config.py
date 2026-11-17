"""Configuración del canal de chat en tiempo real.

Los valores se leen del entorno con defaults seguros. No se tocan ``.env*``
(archivos protegidos); la documentación de diseño recoge las variables para
desplegarlas cuando el equipo las necesite.
"""

from __future__ import annotations

import os

#: Agente que habla por este canal (BRIEFING Parte 2).
AGENT_ID = "first_line_cx"

SESSION_PREFIX = "chat_"
MESSAGE_PREFIX = "msg_"

SESSION_STATUSES = ("active", "interrupted", "closed")
MESSAGE_ROLES = ("user", "assistant")
MESSAGE_STATUSES = ("streaming", "completed", "interrupted", "failed")


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
        return max(0.1, float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


#: Mensajes devueltos por ``session_snapshot`` al conectar o reconectar.
HISTORY_LIMIT = _int_env("CHAT_HISTORY_LIMIT", 50)

#: Turnos previos inyectados en el prompt de generación.
PROMPT_HISTORY_MESSAGES = _int_env("CHAT_PROMPT_HISTORY_MESSAGES", 6)
PROMPT_HISTORY_CHARS = _int_env("CHAT_PROMPT_HISTORY_CHARS", 3_000)

#: Longitud máxima de un mensaje de usuario.
MAX_MESSAGE_CHARS = _int_env("CHAT_MAX_MESSAGE_CHARS", 4_000)

#: Espera máxima del primer frame de auth cuando no hay ``?token=``.
AUTH_TIMEOUT_SECONDS = _float_env("CHAT_AUTH_TIMEOUT_SECONDS", 5.0)

#: Keep-alive de aplicación (evento ``ping``) para detectar conexiones mudas.
KEEPALIVE_SECONDS = _int_env("CHAT_KEEPALIVE_SECONDS", 20)

#: Espera máxima para que el productor observe el aborto antes de un turno nuevo.
ABORT_WAIT_SECONDS = _float_env("CHAT_ABORT_WAIT_SECONDS", 10.0)

#: Cada cuántos tokens se persiste el parcial (para rehidratar tras una caída).
PARTIAL_PERSIST_EVERY = _int_env("CHAT_PARTIAL_PERSIST_EVERY", 20)


__all__ = [
    "ABORT_WAIT_SECONDS",
    "AGENT_ID",
    "AUTH_TIMEOUT_SECONDS",
    "HISTORY_LIMIT",
    "KEEPALIVE_SECONDS",
    "MAX_MESSAGE_CHARS",
    "MESSAGE_PREFIX",
    "MESSAGE_ROLES",
    "MESSAGE_STATUSES",
    "PARTIAL_PERSIST_EVERY",
    "PROMPT_HISTORY_CHARS",
    "PROMPT_HISTORY_MESSAGES",
    "SESSION_PREFIX",
    "SESSION_STATUSES",
]

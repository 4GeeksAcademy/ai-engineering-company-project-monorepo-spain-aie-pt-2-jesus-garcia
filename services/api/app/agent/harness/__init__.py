"""Harness de aseguramiento del agente de CX de TrackFlow.

Capas:

* ``prompt`` — system prompt con jerarquía y dominio de la empresa;
* ``scope`` — clasificación de alcance y mensajes de redirección;
* ``injection`` — detección de cambios de instrucciones;
* ``orders`` — autorización de pedidos por sesión;
* ``external`` — aislamiento de contenido RAG/tools;
* ``output`` — validación de la respuesta final;
* ``observability`` — eventos, logs y contadores;
* ``runtime`` — composición del input/output guard.
"""

from __future__ import annotations

from .observability import metrics, reset_metrics
from .output import validate_output
from .prompt import CX_PROMPT_VERSION, CX_SYSTEM_PROMPT
from .runtime import screen_input

__all__ = [
    "CX_PROMPT_VERSION",
    "CX_SYSTEM_PROMPT",
    "metrics",
    "reset_metrics",
    "screen_input",
    "validate_output",
]

"""Gate determinista de auto-evaluación.

Este gate no decide si un hecho se recuerda: solo decide si merece la pena
hacer la (única) llamada de evaluación en las rutas que no pasan por el LLM
(ticket/stock y sin contexto). La ruta RAG siempre se auto-evalúa dentro de la
misma llamada de generación.
"""

from __future__ import annotations

import re

from .scopes import normalize_text

_CUE_PATTERNS = (
    r"\ben realidad\b",
    r"\bya no\b",
    r"\bya van\b",
    r"\bya llevamos\b",
    r"\bdesde (?:el|la|hace)\b",
    r"\bsiempre (?:quiere|pide|prefiere|solicita)\b",
    r"\bprefiere\b",
    r"\bcorrige\b",
    r"\bcorregir\b",
    r"\bactualiza\b",
    r"\brecuerda\b",
    r"\bten en cuenta\b",
    r"\btened en cuenta\b",
    r"\bes por\b",
    r"\bson por\b",
    r"\bdebido a\b",
    r"\ba causa de\b",
    r"\bdejo de\b",
    r"\bdejó de\b",
    r"\bcambio su\b",
    r"\bcambió su\b",
    r"\bhuelga\b",
    r"\bno cubre\b",
    r"\bno opera\b",
    r"\bya no cubre\b",
    r"\bpatron\b",
    r"\bpatrón\b",
    r"\brecurrente\b",
    r"\brecurrentes\b",
)

_CLOSING_RE = re.compile(
    r"^(?:perfecto|gracias|muchas gracias|ok|vale|entendido|de acuerdo|"
    r"buenisimo|buenísimo)\b",
    re.IGNORECASE,
)

_RESOLVED_RE = re.compile(
    r"\b(?:ya quedo resuelto|ya quedó resuelto|todo correcto|"
    r"queda resuelto|quedó resuelto)\b",
    re.IGNORECASE,
)

_ONE_OFF_TASK_RE = re.compile(
    r"^(?:traduce|traduceme|tradúceme|resume|resumeme|resúmeme|"
    r"reformula|reformulame|reformúlame|escribe|redacta|calcula|"
    r"convierte|pasa a|formatea)\b",
    re.IGNORECASE,
)

_QUESTION_RE = re.compile(r"\?\s*$")


def _has_cue(normalized: str) -> bool:
    return any(re.search(pattern, normalized) for pattern in _CUE_PATTERNS)


def is_memory_candidate(message: str) -> bool:
    """¿Merece la pena evaluar este mensaje como posible memoria?

    Se excluyen cierres, tareas de un solo uso y preguntas puras sin señal
    declarativa. El gate es deliberadamente conservador: un falso negativo en
    una ruta determinista solo significa que se pierde una propuesta; un falso
    positivo cuesta una llamada barata de evaluación.
    """

    text = (message or "").strip()
    if not text:
        return False
    normalized = normalize_text(text)
    words = normalized.split()
    if len(words) < 3:
        return False
    if _CLOSING_RE.match(text.strip()) and len(words) <= 10:
        return False
    if _RESOLVED_RE.search(normalized) and len(words) <= 10:
        return False
    if _ONE_OFF_TASK_RE.match(text.strip()) and not _has_cue(normalized):
        return False
    if _has_cue(normalized):
        return True
    if _QUESTION_RE.search(text) and text.count("?") >= 1:
        return False

    sentences = re.split(r"[.!?;]\s*", text)
    for sentence in sentences:
        candidate = sentence.strip()
        if not candidate or candidate.endswith("?"):
            continue
        if len(candidate.split()) >= 5:
            return True
    return False


__all__ = ["is_memory_candidate"]

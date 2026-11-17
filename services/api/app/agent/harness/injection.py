"""Detección determinista de intentos de secuestro de instrucciones.

El detector se apoya en patrones normalizados (minúsculas, sin acentos, sin
caracteres invisibles) y devuelve la variante encontrada. Se usa dos veces:

* en el input guard, antes de invocar al grafo;
* en el aislamiento de contenido externo (RAG y tools), para neutralizar
  instrucciones incrustadas en documentos o resultados.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def normalize_text(text: str | None) -> str:
    """Minúsculas, sin acentos, sin invisibles y con espacios colapsados."""

    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    without_invisible = _INVISIBLE_RE.sub("", without_accents)
    return re.sub(r"\s+", " ", without_invisible.lower()).strip()


# (variante, patrón). El orden importa: la primera coincidencia gana.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"(?:ignora(?:s|r)?|olvida(?:s|r)?|desobedece|descarta|"
            r"ignore|disregard|forget|override)\s+"
            r"(?:(?:todas|all|tus|your|las|the|mis|my|previous|previas|"
            r"anteriores)\s+){0,4}"
            r"(?:instrucciones|instructions|reglas|rules|directrices|"
            r"guidelines|indicaciones)"
        ),
    ),
    (
        "system_override",
        re.compile(
            r"(?:nuevas?\s+instrucciones|new\s+instructions|"
            r"instrucciones\s+del\s+sistema|system\s+instructions|"
            r"system\s+prompt|prompt\s+del\s+sistema|"
            r"modo\s+desarrollador|developer\s+mode|"
            r"modo\s+dios|god\s+mode|jailbreak|do\s+anything\s+now|\bdan\b)"
        ),
    ),
    (
        "role_change",
        re.compile(
            r"(?:ahora\s+(?:eres|seras|debes|actua|actuaras)|"
            r"a\s+partir\s+de\s+ahora\s+(?:eres|debes|actua)|"
            r"actua\s+como|actuar\s+como|comportate\s+como|"
            r"simula\s+ser|haz\s+de|"
            r"you\s+are\s+now|from\s+now\s+on\s+you\s+are|"
            r"act\s+as|pretend\s+to\s+be|roleplay\s+as)"
        ),
    ),
    (
        "no_rules",
        re.compile(
            r"(?:sin\s+reglas|sin\s+restricciones|sin\s+limites|"
            r"no\s+rules|no\s+restrictions|without\s+restrictions|"
            r"unrestricted|uncensored|sin\s+censura)"
        ),
    ),
    (
        "forget_employer",
        re.compile(
            r"(?:olvida(?:te)?\s+(?:de\s+)?trackflow|"
            r"olvida\s+que\s+trabajas\s+para|"
            r"ya\s+no\s+trabajas\s+para|"
            r"forget\s+(?:about\s+)?trackflow|"
            r"forget\s+(?:that\s+)?you\s+work\s+for)"
        ),
    ),
    (
        "prompt_extraction",
        re.compile(
            r"(?:revela(?:s|r|me)?|muestra(?:s|r|me)?|ensena(?:s|r|me)?|"
            r"repite|copia|imprime|dime|"
            r"reveal|show|print|repeat|leak)\s+"
            r"(?:(?:tu|your|el|the|tus|your)\s+){0,3}"
            r"(?:system\s+prompt|prompt|instrucciones|instructions|"
            r"reglas|rules|configuracion|configuration)"
        ),
    ),
    (
        "fake_system_message",
        re.compile(
            r"(?:^\s*system\s*:|^\s*assistant\s*:|"
            r"^\s*\[\s*system\s*\]|^\s*<\s*system\s*>|"
            r"^\s*###\s*(?:system|sistema)|"
            r"nuevo\s+mensaje\s+del\s+sistema|"
            r"new\s+system\s+message)"
        ),
    ),
    (
        "authority_claim",
        re.compile(
            r"(?:soy\s+(?:el\s+|la\s+)?(?:cto|ceo|admin|administrador|"
            r"desarrollador|developer|responsable|jefe|owner|fundador)|"
            r"i\s+am\s+(?:the\s+)?(?:cto|ceo|admin|developer|owner|founder)|"
            r"autorizado\s+por|authorized\s+by|"
            r"tengo\s+permiso\s+para|i\s+have\s+permission\s+to)"
            r".{0,80}"
            r"(?:ignora(?:s|r)?|ignore|revela(?:s|r)?|reveal|"
            r"sin\s+reglas|no\s+rules|cambia(?:s|r)?|change)"
        ),
    ),
    (
        "obfuscation",
        re.compile(
            r"(?:decodifica\s+y\s+sigue|decode\s+and\s+follow|"
            r"base64.{0,40}(?:sigue|follow|instrucciones|instructions)|"
            r"rot13.{0,40}(?:sigue|follow|instrucciones|instructions))"
        ),
    ),
    (
        "hide_from_user",
        re.compile(
            r"(?:no\s+le\s+digas\s+al\s+usuario|no\s+se\s+lo\s+digas|"
            r"oculta\s+(?:esto|esta\s+regla|estas\s+instrucciones)|"
            r"do\s+not\s+tell\s+the\s+user|hide\s+(?:this|these\s+instructions))"
        ),
    ),
)


@dataclass(frozen=True)
class InjectionMatch:
    kind: str
    snippet: str

    @property
    def reason(self) -> str:
        return f"injection:{self.kind}"


def detect_injection(text: str | None) -> InjectionMatch | None:
    """Devuelve la primera variante de inyección detectada, si la hay."""

    normalized = normalize_text(text)
    if not normalized:
        return None
    for kind, pattern in _PATTERNS:
        match = pattern.search(normalized)
        if match:
            start = max(0, match.start() - 30)
            end = min(len(normalized), match.end() + 30)
            return InjectionMatch(kind=kind, snippet=normalized[start:end])
    return None


def contains_instruction_text(text: str | None) -> bool:
    """True si el texto parece contener una instrucción para el modelo."""

    return detect_injection(text) is not None


__all__ = [
    "InjectionMatch",
    "contains_instruction_text",
    "detect_injection",
    "normalize_text",
]

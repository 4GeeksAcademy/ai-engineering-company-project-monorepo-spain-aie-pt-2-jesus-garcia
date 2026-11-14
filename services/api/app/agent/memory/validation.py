"""Validación determinista de lo que puede y no puede entrar en memoria.

Es la segunda barrera (la primera son las reglas del prompt). Se ejecuta dos
veces: al crear la propuesta y al escribirla tras la aprobación. Un fallo aquí
nunca escribe una entrada; solo deja un registro de auditoría con el motivo.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from . import config
from .scopes import normalize_text
from .schemas import MemoryProposalDraft

# --- Patrones de datos prohibidos -------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}"
)

_STREET_WORD = (
    r"(?:calle|carrer|avenida|avda\.?|plaza|paseo|"
    r"street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|highway|hwy\.?)"
)
_ADDRESS_RE = re.compile(
    rf"\b{_STREET_WORD}\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]",
    re.IGNORECASE,
)
_ADDRESS_NUMBER_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s+){1,3}"
    r"(?:street|st|avenue|ave|road|rd|calle|carrer|avenida)\b",
    re.IGNORECASE,
)
_ADDRESS_REDACT_RE = re.compile(
    rf"\b{_STREET_WORD}\b[^\n.;]*",
    re.IGNORECASE,
)
_POSTAL_RE = re.compile(
    r"\b(?:cp|c\.p\.|codigo postal|código postal|zip)\s*[:#]?\s*\d{4,5}\b",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"\b(?:piso|puerta|portal|escalera|apartamento|apto\.?|suite|unit|floor)"
    r"\s*\d+\b",
    re.IGNORECASE,
)
_COORDINATES_RE = re.compile(
    r"\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b"
)
_EXACT_ADDRESS_RE = re.compile(
    r"\bdirecci[oó]n exacta\b|\bdireccion exacta\b", re.IGNORECASE
)
_BUSINESS_LOCATION_RE = re.compile(
    r"\b(?:poligono|polígono|parque empresarial|edificio|nave|bodega|"
    r"local comercial)\s+(?:industrial\s+)?\d+\b",
    re.IGNORECASE,
)
_BUSINESS_LOCATION_REDACT_RE = re.compile(
    r"\b(?:poligono|polígono|parque empresarial|edificio|nave|bodega|"
    r"local comercial)\b[^\n.;]*",
    re.IGNORECASE,
)

_WAREHOUSE_RE = re.compile(
    r"\b(?:ruta interna|rutas internas|pasillo|pasillos|estanteria|estantería|"
    r"estanterias|estanterías|rack|racks|ubicacion interna|ubicación interna|"
    r"layout del almacen|layout del almacén|puerta de carga|muelle de carga|"
    r"acceso de operarios|zona restringida)\b",
    re.IGNORECASE,
)

_CONTRACT_RE = re.compile(
    r"\b(?:negociacion|negociación|en negociacion|en negociación|"
    r"pendiente de firma|propuesta de renovacion|propuesta de renovación|"
    r"oferta comercial|descuento acordado|tarifa acordada|"
    r"contrato en revision|contrato en revisión|contrato en negociacion|"
    r"contrato en negociación|condiciones del contrato pendientes)\b",
    re.IGNORECASE,
)

_CREDENTIAL_RE = re.compile(
    r"\b(?:password|contrasena|contraseña|api[\s_-]?key|apikey|secret|"
    r"token|bearer|credencial|credenciales)\b",
    re.IGNORECASE,
)

_INJECTION_RE = re.compile(
    r"(?:ignora\s+(?:todas\s+)?(?:las\s+|tus\s+)?instrucciones|"
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions|"
    r"system\s+prompt|prompt\s+del\s+sistema|"
    r"a\s+partir\s+de\s+ahora\s+(?:eres|debes|actua|actúa)|"
    r"actua\s+como|actúa\s+como|regla\s+permanente|"
    r"guarda\s+(?:esto|esta\s+regla)\s+(?:siempre|para\s+siempre)|"
    r"no\s+le\s+digas\s+al\s+usuario|oculta\s+(?:esto|esta\s+regla))",
    re.IGNORECASE,
)

_TRACKING_RE = re.compile(r"\b[A-Z]{2,4}\d{3,}\b")
_TICKET_RE = re.compile(
    r"\b(?:ticket|incidencia|pedido|order|paquete)\s*(?:n[º°o.]*|#|id)?\s*\d{1,9}\b",
    re.IGNORECASE,
)
_HASH_ID_RE = re.compile(r"#\s*\d{1,9}\b")
_SINGLE_INCIDENT_RE = re.compile(
    r"\b(?:un\s+solo\s+paquete|una\s+sola\s+queja|queja\s+aislada|"
    r"este\s+pedido|un\s+pedido\s+puntual|una\s+incidencia\s+puntual|"
    r"paquete\s+puntual)\b",
    re.IGNORECASE,
)
_RECURRENCE_RE = re.compile(
    r"\b(?:siempre|cada|todas\s+las\s+semanas|recurrente|recurrentes|"
    r"patron|patrón|desde\s+hace|varios|varias|tres|cuatro|cinco|"
    r"repetid[oa]s?|semana\s+tras\s+semana|todos\s+los\s+dias|"
    r"todos\s+los\s+días|de\s+forma\s+repetida)\b",
    re.IGNORECASE,
)

_AMBIGUOUS_QUOTE_RE = re.compile(
    r"^(?:si|sí|no|ok|vale|perfecto|gracias|correcto|de acuerdo|"
    r"adelante|guardalo|guárdalo|recuerdalo|recuérdalo)[.! ]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationIssue:
    ok: bool
    code: str | None = None
    detail: str | None = None


def _ok() -> ValidationIssue:
    return ValidationIssue(ok=True)


def _fail(code: str, detail: str) -> ValidationIssue:
    return ValidationIssue(ok=False, code=code, detail=detail)


def _normalize_for_match(text: str) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def message_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def redact_text(text: str | None, *, limit: int | None = None) -> str:
    """Sanea un texto para auditoría/trazas sin destruir su utilidad."""

    if not text:
        return ""
    result = str(text)
    result = _EMAIL_RE.sub("[REDACTED_EMAIL]", result)
    result = _COORDINATES_RE.sub("[REDACTED_COORDINATES]", result)
    result = _ADDRESS_REDACT_RE.sub("[REDACTED_ADDRESS]", result)
    result = _BUSINESS_LOCATION_REDACT_RE.sub("[REDACTED_ADDRESS]", result)
    result = _ADDRESS_NUMBER_RE.sub("[REDACTED_ADDRESS]", result)
    result = _POSTAL_RE.sub("[REDACTED_POSTAL_CODE]", result)

    def _phone(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 9:
            return "[REDACTED_PHONE]"
        return candidate

    result = _PHONE_RE.sub(_phone, result)
    result = _CREDENTIAL_RE.sub("[REDACTED_SECRET]", result)
    if limit is not None and len(result) > limit:
        result = result[: max(0, limit - 1)].rstrip() + "…"
    return result


def contains_forbidden(text: str | None, *, memory_type: str | None = None) -> str | None:
    """Devuelve el código de la primera categoría prohibida encontrada."""

    if not text:
        return None
    value = str(text)

    if _CREDENTIAL_RE.search(value):
        return "credentials"
    if _EMAIL_RE.search(value):
        return "personal_data_email"
    phone_match = _PHONE_RE.search(value)
    if phone_match:
        digits = re.sub(r"\D", "", phone_match.group(0))
        if len(digits) >= 9:
            return "personal_data_phone"
    if _EXACT_ADDRESS_RE.search(value):
        return "exact_address"
    if _BUSINESS_LOCATION_RE.search(value):
        return "exact_address"
    if (
        _ADDRESS_RE.search(value)
        or _ADDRESS_NUMBER_RE.search(value)
        or _POSTAL_RE.search(value)
        or _UNIT_RE.search(value)
        or _COORDINATES_RE.search(value)
    ):
        return "exact_address"
    if _WAREHOUSE_RE.search(value):
        return "internal_warehouse_route"
    if _CONTRACT_RE.search(value):
        return "contract_negotiation"
    if _INJECTION_RE.search(value):
        return "prompt_injection"

    has_identifier = bool(
        _TRACKING_RE.search(value)
        or _TICKET_RE.search(value)
        or _HASH_ID_RE.search(value)
    )
    has_recurrence = bool(_RECURRENCE_RE.search(value))
    if _SINGLE_INCIDENT_RE.search(value) and not has_recurrence:
        return "single_incident"
    if has_identifier and not has_recurrence:
        if memory_type != "operational_context":
            return "single_incident"
        return "single_incident"
    return None


def quote_is_grounded(quote: str, message: str) -> bool:
    """La cita debe ser una subcadena literal (normalizada) del mensaje."""

    normalized_quote = _normalize_for_match(quote)
    normalized_message = _normalize_for_match(message)
    if len(normalized_quote) < 12:
        return False
    if len(normalized_quote.split()) < 4:
        return False
    return normalized_quote in normalized_message


def _validate_core(
    draft: MemoryProposalDraft,
    *,
    message: str | None,
    require_quote: bool,
) -> ValidationIssue:
    if draft.memory_type not in config.MEMORY_TYPES:
        return _fail("invalid_type", "Tipo de memoria no permitido.")

    expected_scope = {
        "carrier_rule": "carrier",
        "operational_context": "ops",
        "client_preference": "client",
    }[draft.memory_type]
    if draft.scope.kind != expected_scope:
        return _fail(
            "invalid_scope",
            "El alcance no corresponde al tipo de memoria.",
        )
    if not draft.scope.key or ":" not in draft.scope.key:
        return _fail("invalid_scope", "El alcance no está normalizado.")
    if draft.scope.key.startswith(("global", "all")):
        return _fail("invalid_scope", "No se permite memoria global.")

    fact = (draft.fact or "").strip()
    if len(fact) < 8:
        return _fail("fact_too_short", "El hecho es demasiado corto.")
    if len(fact) > config.MAX_FACT_CHARS:
        return _fail("fact_too_long", "El hecho excede el tamaño permitido.")

    forbidden = contains_forbidden(fact, memory_type=draft.memory_type)
    if forbidden:
        return _fail(forbidden, "El hecho contiene información prohibida.")

    if draft.reason:
        if len(draft.reason) > config.MAX_REASON_CHARS:
            return _fail("reason_too_long", "El motivo excede el tamaño permitido.")
        forbidden = contains_forbidden(
            draft.reason, memory_type=draft.memory_type
        )
        if forbidden:
            return _fail(
                f"reason_{forbidden}",
                "El motivo contiene información prohibida.",
            )

    quote = (draft.source_quote or "").strip()
    if len(quote) > config.MAX_QUOTE_CHARS:
        return _fail("quote_too_long", "La cita excede el tamaño permitido.")
    if require_quote:
        if _AMBIGUOUS_QUOTE_RE.match(quote):
            return _fail("quote_not_specific", "La cita no identifica un hecho.")
        forbidden = contains_forbidden(quote, memory_type=draft.memory_type)
        if forbidden:
            return _fail(
                f"quote_{forbidden}",
                "La cita contiene información prohibida.",
            )
        if not quote_is_grounded(quote, message or ""):
            return _fail(
                "not_grounded",
                "La cita no aparece literalmente en el mensaje del usuario.",
            )

    return _ok()


def validate_proposal(
    draft: MemoryProposalDraft,
    message: str,
) -> ValidationIssue:
    """Valida un borrador completo contra el mensaje que lo originó."""

    return _validate_core(draft, message=message, require_quote=True)


def validate_for_write(
    draft: MemoryProposalDraft,
    *,
    original_message: str | None,
) -> ValidationIssue:
    """Revalidación antes de escribir.

    La aprobación ya verificó la cita contra el mensaje original; aquí se
    revalidan estructura, alcance y contenido prohibido. Si se dispone del
    mensaje original (sin redactar) también se comprueba la cita.
    """

    return _validate_core(
        draft,
        message=original_message,
        require_quote=bool(original_message),
    )


__all__ = [
    "ValidationIssue",
    "contains_forbidden",
    "message_hash",
    "quote_is_grounded",
    "redact_text",
    "validate_for_write",
    "validate_proposal",
]

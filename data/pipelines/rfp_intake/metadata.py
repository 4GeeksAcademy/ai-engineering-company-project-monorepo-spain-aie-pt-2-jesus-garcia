"""Agente de extracción de metadatos de la RFP.

El LLM propone; la normalización es determinista y conservadora: país, moneda,
volumen, fecha y presupuesto se validan contra el texto y, si no constan, se
quedan en ``None``. Nunca se rellenan cifras por defecto.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from .catalog import (
    currency_for_country,
    departments_for_services,
    normalize_country,
    normalize_services,
)
from .llm import JsonLlm, LlmError

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 24_000
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTHS = {
    "enero": "january",
    "febrero": "february",
    "marzo": "march",
    "abril": "april",
    "mayo": "may",
    "junio": "june",
    "julio": "july",
    "agosto": "august",
    "septiembre": "september",
    "setiembre": "september",
    "octubre": "october",
    "noviembre": "november",
    "diciembre": "december",
}

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d %B %Y",
    "%B %d, %Y",
    "%B %d %Y",
    "%d %b %Y",
    "%b %d, %Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
)

SYSTEM_PROMPT = """Eres el extractor de metadatos de RFPs de TrackFlow. Recibirás una RFP ya clasificada como válida y su clasificación inicial.

Extrae EXCLUSIVAMENTE lo que el documento dice. No completes datos, no estimes cifras y no inventes presupuestos, volúmenes ni fechas. Si un dato no aparece, devuélvelo como null y añade el campo a missing_fields.

Devuelve EXCLUSIVAMENTE este objeto JSON:
{
  "client_name": "nombre de la empresa o null",
  "client_country": "US" | "Spain" | null,
  "language": "es" | "en",
  "services_requested": ["warehousing" | "last_mile" | "reverse_logistics"],
  "unknown_services": ["servicios mencionados fuera del catálogo"],
  "monthly_volume": número entero de pedidos/envíos al mes o null,
  "sku_count": número entero de SKUs o null,
  "return_volume": número entero de devoluciones al mes o null,
  "return_rate": porcentaje numérico de devoluciones o null,
  "deadline": "YYYY-MM-DD" o null,
  "budget_range": "texto literal del presupuesto o null",
  "contact": {"name": "...", "role": "...", "email": "..."},
  "scope_notes": ["condiciones operativas relevantes, literales o parafraseadas"],
  "evidence": ["citas literales que respaldan los datos extraídos"],
  "missing_fields": ["monthly_volume", "budget_range", "deadline", "client_country", ...]
}

Reglas:
1. client_country solo puede ser "US" (Estados Unidos) o "Spain" (España). Si el documento no lo deja claro, null.
2. El país determina la moneda; no la inventes aquí.
3. monthly_volume es pedidos o envíos por mes, no SKUs ni devoluciones.
4. No conviertas "3 semanas" en una fecha si el documento no da una fecha concreta; si da una fecha, normalízala a YYYY-MM-DD.
5. No incluyas texto fuera del objeto JSON."""


class MetadataError(RuntimeError):
    """No se pudieron extraer metadatos utilizables."""


def parse_int(value: object) -> int | None:
    """Convierte '5,000', '5.000' o '15000' a entero positivo."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None
    if not isinstance(value, str):
        return None
    match = re.search(r"\d[\d.,]*", value)
    if not match:
        return None
    raw = match.group(0).rstrip(".,")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        normalized = re.sub(r"[.,]", "", raw)
    elif re.fullmatch(r"\d+[.,]\d{1,2}", raw):
        normalized = re.sub(r"[.,]\d{1,2}$", "", raw)
    else:
        normalized = re.sub(r"[.,]", "", raw)
    try:
        number = int(normalized)
    except ValueError:
        return None
    return number if number > 0 else None


def parse_rate(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if 0 < float(value) <= 100 else None
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", value)
    if not match:
        return None
    try:
        rate = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    return rate if 0 < rate <= 100 else None


def parse_deadline(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if ISO_DATE_RE.match(text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    lowered = text.lower()
    for spanish, english in _MONTHS.items():
        lowered = lowered.replace(spanish, english)
    lowered = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", lowered)
    lowered = lowered.replace(" de ", " ").replace(".", "")
    for fmt in _DATE_FORMATS:
        try:
            from datetime import datetime

            return datetime.strptime(lowered, fmt).date().isoformat()
        except ValueError:
            continue
    current_year = date.today().year
    for fmt in ("%B %d", "%d %B", "%b %d", "%d %b"):
        try:
            from datetime import datetime

            return datetime.strptime(
                f"{lowered} {current_year}", f"{fmt} %Y"
            ).date().isoformat()
        except ValueError:
            continue
    return None


def _first_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _contact(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key in ("name", "role", "email"):
        text = _first_string(value.get(key))
        if text:
            result[key] = text
    return result


def _clean_list(value: object, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return cleaned[:limit]


def _detect_language(text: str) -> str:
    lowered = text.lower()
    spanish_hits = sum(
        lowered.count(word)
        for word in (" el ", " la ", " los ", " las ", " de ", " para ", " con ")
    )
    english_hits = sum(
        lowered.count(word)
        for word in (" the ", " and ", " for ", " with ", " we ", " you ")
    )
    return "es" if spanish_hits >= english_hits else "en"


def _regex_monthly_volume(text: str) -> int | None:
    patterns = (
        r"(\d[\d.,]*)\s*(?:pedidos|orders|env[ií]os|paquetes|packages)\s*(?:al|por|per|a|/)?\s*(?:mes|month)",
        r"(?:pedidos|orders|env[ií]os|paquetes|packages)\D{0,20}(\d[\d.,]*)\s*(?:al|por|per|a|/)?\s*(?:mes|month)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_int(match.group(1))
    return None


def _regex_sku_count(text: str) -> int | None:
    match = re.search(
        r"(\d[\d.,]*)\s*(?:skus?|referencias?|referencias|products?|productos?)",
        text,
        flags=re.IGNORECASE,
    )
    return parse_int(match.group(1)) if match else None


def _regex_return_rate(text: str) -> float | None:
    match = re.search(
        r"(?:devoluciones|returns?)\D{0,30}(\d+(?:[.,]\d+)?)\s*%",
        text,
        flags=re.IGNORECASE,
    )
    return parse_rate(match.group(1)) if match else None


def _regex_return_volume(text: str) -> int | None:
    match = re.search(
        r"(\d[\d.,]*)\s*(?:devoluciones|returns?)\s*(?:al|por|per|/|a)?\s*(?:mes|month)?",
        text,
        flags=re.IGNORECASE,
    )
    return parse_int(match.group(1)) if match else None

def _regex_deadline(text: str) -> str | None:
    patterns = (
        r"(?:proposal due date|due date|deadline|fecha l[ií]mite|antes del|hacia el|around|by)\s*:?\s*([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)",
        r"(?:proposal due date|due date|deadline|fecha l[ií]mite|antes del|hacia el|around|by)\s*:?\s*(\d{1,2}\s+de\s+[A-Za-z]+(?:\s+de\s+\d{4})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            parsed = parse_deadline(match.group(1))
            if parsed:
                return parsed
    return None


def normalize_metadata(
    payload: dict,
    classification: dict,
    markdown: str,
) -> dict:
    services, unknown = normalize_services(payload.get("services_requested"))
    for service in classification.get("services_requested", []):
        if service not in services:
            services.append(service)
    for item in payload.get("unknown_services") or []:
        if isinstance(item, str) and item.strip() and item not in unknown:
            unknown.append(item.strip())
    for item in classification.get("unknown_services") or []:
        if item not in unknown:
            unknown.append(item)

    country = normalize_country(payload.get("client_country")) or normalize_country(
        classification.get("client_country")
    )
    client_name = _first_string(payload.get("client_name")) or _first_string(
        classification.get("client_name")
    )

    monthly_volume = parse_int(payload.get("monthly_volume"))
    if monthly_volume is None:
        monthly_volume = _regex_monthly_volume(markdown)

    sku_count = parse_int(payload.get("sku_count"))
    if sku_count is None:
        sku_count = _regex_sku_count(markdown)

    return_volume = parse_int(payload.get("return_volume"))
    if return_volume is None:
        return_volume = _regex_return_volume(markdown)

    return_rate = parse_rate(payload.get("return_rate"))
    if return_rate is None:
        return_rate = _regex_return_rate(markdown)

    deadline = parse_deadline(payload.get("deadline"))
    if deadline is None:
        deadline = _regex_deadline(markdown)
    budget_range = _first_string(payload.get("budget_range"))
    language = _first_string(payload.get("language"))
    if language not in {"es", "en"}:
        language = _detect_language(markdown)

    missing_fields: list[str] = []
    for field, value in (
        ("client_name", client_name),
        ("client_country", country),
        ("monthly_volume", monthly_volume),
        ("deadline", deadline),
        ("budget_range", budget_range),
    ):
        if value in (None, ""):
            missing_fields.append(field)

    return {
        "client_name": client_name,
        "client_country": country,
        "currency": currency_for_country(country),
        "language": language,
        "services_requested": services,
        "unknown_services": unknown,
        "departments_needed": departments_for_services(services),
        "monthly_volume": monthly_volume,
        "sku_count": sku_count,
        "return_volume": return_volume,
        "return_rate": return_rate,
        "deadline": deadline,
        "budget_range": budget_range,
        "contact": _contact(payload.get("contact")),
        "scope_notes": _clean_list(payload.get("scope_notes")),
        "evidence": _clean_list(payload.get("evidence"), limit=10),
        "missing_fields": missing_fields,
    }


def extract_metadata(
    markdown: str,
    classification: dict,
    llm: JsonLlm,
) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Clasificación inicial:\n"
                f"{classification}\n\n"
                f"--- RFP ---\n{markdown[:MAX_INPUT_CHARS]}\n--- FIN ---"
            ),
        },
    ]
    try:
        payload = llm(messages, max_tokens=1_400, temperature=0.0)
    except LlmError as exc:
        raise MetadataError(f"La extracción de metadatos falló: {exc}") from exc
    metadata = normalize_metadata(payload, classification, markdown)
    logger.info(
        "rfp_intake metadata client=%s country=%s services=%s volume=%s",
        metadata["client_name"],
        metadata["client_country"],
        metadata["services_requested"],
        metadata["monthly_volume"],
    )
    return metadata

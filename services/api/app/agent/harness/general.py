"""Respuestas deterministas para small talk, hora y conceptos de logística.

No se llama al LLM: estas consultas están permitidas pero deben cerrarse
siempre con una redirección al propósito del agente. La hora se calcula con
``zoneinfo`` y, si el sistema no trae tzdata, con offsets fijos.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .injection import normalize_text
from .scope import REDIRECT_LINE

_CITY_ZONES: dict[str, str] = {
    "tokio": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "madrid": "Europe/Madrid",
    "zaragoza": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "valencia": "Europe/Madrid",
    "sevilla": "Europe/Madrid",
    "los angeles": "America/Los_Angeles",
    "los angeles california": "America/Los_Angeles",
    "nueva york": "America/New_York",
    "new york": "America/New_York",
    "miami": "America/New_York",
    "londres": "Europe/London",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "roma": "Europe/Rome",
    "lisboa": "Europe/Lisbon",
    "ciudad de mexico": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "bogota": "America/Bogota",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "lima": "America/Lima",
    "santiago": "America/Santiago",
    "sydney": "Australia/Sydney",
    "singapur": "Asia/Singapore",
    "singapore": "Asia/Singapore",
    "dubai": "Asia/Dubai",
}

_FALLBACK_OFFSETS: dict[str, int] = {
    "Asia/Tokyo": 9,
    "Europe/Madrid": 1,
    "America/Los_Angeles": -8,
    "America/New_York": -5,
    "Europe/London": 0,
    "Europe/Paris": 1,
    "Europe/Berlin": 1,
    "Europe/Rome": 1,
    "Europe/Lisbon": 0,
    "America/Mexico_City": -6,
    "America/Bogota": -5,
    "America/Argentina/Buenos_Aires": -3,
    "America/Lima": -5,
    "America/Santiago": -4,
    "Australia/Sydney": 10,
    "Asia/Singapore": 8,
    "Asia/Dubai": 4,
}

_TIME_RE = re.compile(
    r"(?:que hora es|qué hora es|what time is it|hora actual|hora es)"
    r"\s+(?:en\s+)?([a-z0-9áéíóúüñ\s]+?)(?:[?.!]|$)",
    re.IGNORECASE,
)

_GLOSSARY: dict[str, str] = {
    "logistica inversa": (
        "La logística inversa es el proceso de gestionar el retorno de "
        "productos desde el cliente final hasta el almacén o el fabricante "
        "(devoluciones, reciclaje y reacondicionamiento). En TrackFlow se "
        "aplica a las devoluciones de pedidos y a su inspección."
    ),
    "ultima milla": (
        "La última milla es el tramo final de la entrega, desde el centro de "
        "reparto hasta la puerta del destinatario. En TrackFlow es donde se "
        "concentran los SLA y las incidencias de entrega."
    ),
    "cross docking": (
        "El cross-docking es una técnica en la que la mercancía pasa por el "
        "almacén sin almacenarse, para pasar de un transporte a otro. En "
        "TrackFlow ayuda a reducir tiempos en pedidos urgentes."
    ),
    "picking": (
        "El picking es la recogida de los productos de sus ubicaciones en el "
        "almacén para preparar un pedido. En TrackFlow forma parte del flujo "
        "de preparación antes del empaquetado."
    ),
    "packing": (
        "El packing es el empaquetado de los productos ya recogidos, con "
        "protección y documentación. En TrackFlow se hace antes de entregar "
        "el pedido al transportista."
    ),
    "wms": (
        "Un WMS es un sistema de gestión de almacén que controla stock, "
        "ubicaciones y movimientos. TrackFlow está unificando los dos "
        "sistemas de sus almacenes."
    ),
    "sla": (
        "Un SLA es un acuerdo de nivel de servicio: el compromiso medible de "
        "plazo y calidad. En TrackFlow el SLA estándar es de 3 a 5 días "
        "hábiles dentro del mismo país, con un 90 % de entregas a tiempo."
    ),
    "incoterm": (
        "Los incoterms son reglas internacionales que reparten "
        "responsabilidades y costes entre comprador y vendedor. En TrackFlow "
        "afectan a envíos internacionales y aduanas."
    ),
    "fulfillment": (
        "El fulfillment es la externalización de la preparación y envío de "
        "pedidos. Es el servicio principal que TrackFlow presta a las marcas "
        "de e-commerce."
    ),
    "dropshipping": (
        "El dropshipping es un modelo en el que el vendedor no guarda stock y "
        "el pedido se prepara desde un tercero. TrackFlow puede actuar como "
        "operador logístico de esa marca."
    ),
    "almacenaje": (
        "El almacenaje es el servicio de guardar inventario en un almacén y "
        "gestionar sus movimientos. TrackFlow lo cobra por volumen ocupado."
    ),
    "cadena de suministro": (
        "La cadena de suministro es el conjunto de pasos desde el proveedor "
        "hasta el cliente final. TrackFlow cubre almacenaje, preparación, "
        "transporte y devoluciones."
    ),
    "tracking": (
        "El tracking es el seguimiento del envío mediante un número de "
        "seguimiento. En TrackFlow puedes consultarlo con el número de "
        "pedido o de guía."
    ),
    "aduana": (
        "La aduana es el control fronterizo de mercancías y documentos. En "
        "TrackFlow los envíos internacionales pueden retenerse y el tiempo "
        "de retención no depende de la empresa."
    ),
}


def _normalized_city(candidate: str) -> str | None:
    city = normalize_text(candidate)
    city = re.sub(r"\b(?:en|el|la|de|del)\b", " ", city)
    city = re.sub(r"\s+", " ", city).strip(" ?.!,")
    for key in sorted(_CITY_ZONES, key=len, reverse=True):
        if key in city:
            return key
    return None


def _local_time(zone_name: str) -> str | None:
    try:
        zone = ZoneInfo(zone_name)
        now = datetime.now(zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        offset = _FALLBACK_OFFSETS.get(zone_name)
        if offset is None:
            return None
        now = datetime.now(timezone.utc).astimezone(
            timezone(timedelta(hours=offset))
        )
    return now.strftime("%H:%M")


def answer_time(question: str) -> str | None:
    """Responde la hora local de una ciudad conocida, con redirección."""

    match = _TIME_RE.search(question or "")
    if not match:
        return None
    city_key = _normalized_city(match.group(1))
    if city_key is None:
        return None
    zone_name = _CITY_ZONES[city_key]
    local = _local_time(zone_name)
    if local is None:
        return None
    city_label = city_key.title()
    return f"En {city_label} son las {local} (hora local).\n\n{REDIRECT_LINE}"


def answer_general_logistics(question: str) -> str | None:
    """Definición breve de un concepto logístico + redirección."""

    normalized = normalize_text(question)
    for term in sorted(_GLOSSARY, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            return f"{_GLOSSARY[term]}\n\n{REDIRECT_LINE}"
    return None


def answer_casual(question: str) -> str | None:
    """Small talk breve que siempre reconduce al propósito del agente."""

    normalized = normalize_text(question)
    if not normalized:
        return None
    if re.search(r"\b(gracias|thanks|thank you)\b", normalized):
        return (
            "De nada. Si necesitas algo sobre tu envío, una devolución o una "
            f"incidencia, aquí estoy.\n\n{REDIRECT_LINE}"
        )
    if re.search(
        r"\b(quien eres|quien eres tu|que haces|cual es tu funcion|"
        r"para que sirves|que puedes hacer)\b",
        normalized,
    ):
        return (
            "Soy el agente de soporte logístico de TrackFlow. Puedo ayudarte "
            "con el estado de tu pedido, devoluciones, SLAs por país e "
            f"incidencias.\n\n{REDIRECT_LINE}"
        )
    if re.search(
        r"\b(hola|buenas|buenos dias|buenas tardes|buenas noches|"
        r"que tal|hey|hi|hello)\b",
        normalized,
    ):
        return (
            "Hola. Puedo ayudarte con el estado de tu pedido, devoluciones, "
            f"SLAs por país e incidencias. ¿Qué necesitas?\n\n{REDIRECT_LINE}"
        )
    if re.search(
        r"\b(adios|hasta luego|nos vemos|bye|goodbye)\b", normalized
    ):
        return (
            "Hasta luego. Si más adelante necesitas ayuda con un envío, una "
            f"devolución o una incidencia, aquí estaré.\n\n{REDIRECT_LINE}"
        )
    return None


def answer_general(question: str, kind: str) -> str:
    """Respuesta determinista para una consulta permitida fuera de dominio."""

    time_answer = answer_time(question)
    if time_answer:
        return time_answer
    if kind == "casual":
        return answer_casual(question) or (
            f"Estoy aquí para ayudarte con TrackFlow.\n\n{REDIRECT_LINE}"
        )
    if kind == "general_logistics":
        return answer_general_logistics(question) or (
            f"No tengo una definición cerrada de ese concepto, pero en "
            f"TrackFlow lo aplicamos a envíos, devoluciones e incidencias.\n\n"
            f"{REDIRECT_LINE}"
        )
    return answer_time(question) or (
        f"No puedo responder a esa curiosidad con fiabilidad, pero mi "
        f"función es ayudarte con envíos, devoluciones e incidencias de "
        f"TrackFlow.\n\n{REDIRECT_LINE}"
    )


__all__ = [
    "answer_casual",
    "answer_general",
    "answer_general_logistics",
    "answer_time",
]

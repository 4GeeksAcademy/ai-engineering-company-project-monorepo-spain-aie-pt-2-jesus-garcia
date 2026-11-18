"""Clasificación determinista de alcance y mensajes de rechazo/redirección.

El clasificador es deliberadamente conservador con los bloqueos: solo rechaza
cuando hay una señal clara (tarea personal, inyección, pedido ajeno o consulta
general fuera de logística). Ante la duda deja pasar la consulta al grafo, que
responderá con honestidad si el RAG no tiene contexto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .injection import normalize_text

ScopeKind = Literal[
    "in_domain",
    "casual",
    "general_logistics",
    "personal_use",
    "out_of_domain",
]

PERSONAL_USE_REFUSAL = (
    "No puedo ayudarte con eso: soy el agente de soporte logístico de "
    "TrackFlow y solo respondo sobre envíos, devoluciones e incidencias. Si "
    "tu consulta es sobre un pedido, una devolución o una incidencia, dímelo "
    "y lo revisamos."
)

OUT_OF_DOMAIN_REDIRECT = (
    "Eso queda fuera de mi ámbito. Soy el agente de soporte logístico de "
    "TrackFlow: puedo ayudarte con el estado de tu pedido, devoluciones, "
    "SLAs por país e incidencias."
)

REDIRECT_LINE = (
    "Si tu consulta es sobre un envío, una devolución o una incidencia de "
    "TrackFlow, puedo ayudarte con eso."
)

_DOMAIN_TERMS = (
    "trackflow",
    "pedido",
    "pedidos",
    "order",
    "orders",
    "tracking",
    "seguimiento",
    "envio",
    "envios",
    "enviar",
    "envia",
    "enviaste",
    "shipment",
    "shipments",
    "parcel",
    "paquete",
    "paquetes",
    "entrega",
    "entregas",
    "reparto",
    "guia",
    "guia de envio",
    "devolucion",
    "devoluciones",
    "devolver",
    "retorno",
    "reembolso",
    "reembolsos",
    "refund",
    "return",
    "returns",
    "sla",
    "slas",
    "plazo",
    "plazos",
    "aduanas",
    "aduana",
    "incidencia",
    "incidencias",
    "ticket",
    "tickets",
    "averia",
    "averias",
    "reclamacion",
    "reclamaciones",
    "paquete perdido",
    "entrega fallida",
    "direccion incorrecta",
    "stock",
    "inventario",
    "inventory",
    "sku",
    "skus",
    "existencias",
    "disponibilidad",
    "almacen",
    "almacenes",
    "warehouse",
    "transportista",
    "transportistas",
    "carrier",
    "carriers",
    "ups",
    "fedex",
    "dhl",
    "mrw",
    "seur",
    "marca",
    "marcas",
    "destinatario",
    "destinatarios",
    "consumidor final",
    "cliente b2b",
    "cliente b2c",
    "logistica inversa",
    "ultima milla",
)

_GENERAL_LOGISTICS_CONCEPTS = (
    "logistica inversa",
    "ultima milla",
    "cross docking",
    "cross-docking",
    "picking",
    "packing",
    "wms",
    "sla",
    "incoterm",
    "incoterms",
    "fulfillment",
    "dropshipping",
    "almacenaje",
    "cadena de suministro",
    "inventario",
    "tracking",
    "aduana",
)

# Objetos inequívocamente personales: se bloquean aunque mencionen el dominio
# ("escríbeme un poema sobre paquetes").
_UNAMBIGUOUS_PERSONAL_OBJECTS = (
    "poema",
    "poemas",
    "cuento",
    "cuentos",
    "cancion",
    "canciones",
    "novela",
    "ensayo",
    "ensayos",
    "tesis",
    "redaccion",
    "carta de amor",
    "discurso",
    "chiste",
    "chistes",
    "guion",
    "deberes",
    "homework",
    "examen",
    "universidad",
    "colegio",
    "instituto",
    "asignatura",
    "matematicas",
    "fisica",
    "quimica",
    "filosofia",
    "literatura",
    "receta",
    "recetas",
    "dieta",
    "plan de entrenamiento",
    "rutina de ejercicio",
    "consejo personal",
    "consejos personales",
    "mi relacion",
    "mi pareja",
    "mi salud",
    "medicamento",
    "inversion",
    "inversiones",
    "criptomoneda",
    "criptomonedas",
    "apuesta",
    "apuestas",
    "modo chatbot",
    "asistente personal",
    "chatgpt",
)

# Objetos de programación: solo se bloquean si hay una petición explícita
# ("hazme un script"), no si el usuario pregunta por una integración.
_CODE_TASK_OBJECTS = (
    "codigo",
    "script",
    "programa",
    "algoritmo",
    "funcion",
    "python",
    "javascript",
    "typescript",
    "java",
)

_TASK_VERB_RE = re.compile(
    r"(?:escríbeme|escribeme|redacta|redactame|hazme|haz|resuelve|"
    r"resuelveme|ayudame con|ayudame a|necesito que|quiero que|genera|"
    r"crea|inventa|traduce|traducem[eé]|corrige|resume|explicame|"
    r"write|make|solve|help me with|help me to|i need you to|"
    r"generate|create|invent|translate|correct|summarize|explain)"
)

_CASUAL_TERMS = (
    "hola",
    "holaa",
    "buenas",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "que tal",
    "como estas",
    "hey",
    "hi",
    "hello",
    "gracias",
    "muchas gracias",
    "thanks",
    "thank you",
    "adios",
    "hasta luego",
    "nos vemos",
    "bye",
    "goodbye",
    "quien eres",
    "quien eres tu",
    "que haces",
    "en que puedes ayudar",
    "me puedes ayudar",
    "puedes ayudarme",
    "estas ahi",
)

_GENERAL_KNOWLEDGE_RE = re.compile(
    r"(?:quien es|quien fue|capital(?: de)?|historia de|significado de|"
    r"como se dice|traduce(?:me)? al|clima|el tiempo en|"
    r"noticias|futbol|deporte|pelicula|serie|musica|"
    r"coche|casa|hipoteca|impuestos|elecciones|"
    r"avion privado|alquiler de|precio de(?! envio| pedido| devolucion)|"
    r"cuanto cuesta(?! el envio| un envio| el pedido| la devolucion)|"
    r"receta de|dieta|viaje a|hotel|vuelo|"
    r"que es(?! la logistica| el sla| el tracking| el inventario))"
)

_HELP_OR_IDENTITY_RE = re.compile(
    r"(?:ayuda|ayudar|ayudarme|soporte|agente|que puedes hacer|"
    r"cual es tu funcion|para que sirves)"
)

_TIME_QUESTION_RE = re.compile(
    r"(?:\bque hora es\b|\bque horas son\b|what time is it|"
    r"\bhora actual\b|\bhora es en\b)"
)


@dataclass(frozen=True)
class ScopeDecision:
    kind: ScopeKind
    reason: str
    redirect_required: bool = False

    @property
    def is_domain(self) -> bool:
        return self.kind == "in_domain"


def _contains_any(normalized: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            return True
    return False


def _has_strong_personal_object(normalized: str) -> str | None:
    for term in _UNAMBIGUOUS_PERSONAL_OBJECTS:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            return term
    return None


def _has_code_task_object(normalized: str) -> str | None:
    for term in _CODE_TASK_OBJECTS:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
            return term
    return None


def _has_domain_signal(normalized: str) -> bool:
    return _contains_any(normalized, _DOMAIN_TERMS)


def _has_general_logistics_signal(normalized: str) -> bool:
    if not _contains_any(normalized, _GENERAL_LOGISTICS_CONCEPTS):
        return False
    # Si la pregunta es específica de TrackFlow, es dominio, no curiosidad.
    if _contains_any(
        normalized,
        (
            "trackflow",
            "vuestro",
            "vuestra",
            "nuestro",
            "nuestra",
            "mi pedido",
            "mi envio",
            "mi devolucion",
            "mi cuenta",
            "cliente",
        ),
    ):
        return False
    return bool(
        re.search(
            r"(?:que es|que significa|definicion de|explicame|"
            r"como funciona|what is|definition of)",
            normalized,
        )
    )


def classify_scope(question: str) -> ScopeDecision:
    """Clasifica la consulta en dominio, casual, general o prohibida."""

    normalized = normalize_text(question)
    if not normalized:
        return ScopeDecision("in_domain", "empty_question")

    # 1. Tareas personales: ganan incluso si mencionan palabras del dominio
    #    ("escríbeme un poema sobre paquetes").
    personal_object = _has_strong_personal_object(normalized)
    if personal_object:
        return ScopeDecision(
            "personal_use", f"personal_object:{personal_object}"
        )

    has_domain = _has_domain_signal(normalized)
    if _TASK_VERB_RE.search(normalized):
        code_object = _has_code_task_object(normalized)
        if code_object:
            return ScopeDecision(
                "personal_use", f"personal_code_task:{code_object}"
            )
        if not has_domain:
            return ScopeDecision("personal_use", "personal_task_without_domain")

    # 2. Preguntas generales de logística con redirección.
    if _has_general_logistics_signal(normalized):
        return ScopeDecision(
            "general_logistics",
            "general_logistics_concept",
            redirect_required=True,
        )

    # 3. Dominio de la empresa.
    if has_domain:
        return ScopeDecision("in_domain", "domain_signal")

    # 4. Small talk / identidad / ayuda / hora en una ciudad.
    if _TIME_QUESTION_RE.search(normalized):
        return ScopeDecision("casual", "time_question", redirect_required=True)
    if _contains_any(normalized, _CASUAL_TERMS) and len(normalized.split()) <= 12:
        return ScopeDecision("casual", "casual_conversation", redirect_required=True)
    if _HELP_OR_IDENTITY_RE.search(normalized) and len(normalized.split()) <= 12:
        return ScopeDecision("casual", "help_identity", redirect_required=True)

    # 5. Conocimiento general fuera de logística.
    if _GENERAL_KNOWLEDGE_RE.search(normalized):
        return ScopeDecision(
            "out_of_domain", "general_knowledge", redirect_required=True
        )

    # 6. Preguntas abiertas sin señal de dominio: se dejan pasar al RAG. El
    #    agente responderá con honestidad si no hay contexto; es preferible a
    #    bloquear una consulta legítima corta ("¿cuánto tarda?").
    return ScopeDecision("in_domain", "default_allow")


__all__ = [
    "OUT_OF_DOMAIN_REDIRECT",
    "PERSONAL_USE_REFUSAL",
    "REDIRECT_LINE",
    "ScopeDecision",
    "ScopeKind",
    "classify_scope",
]

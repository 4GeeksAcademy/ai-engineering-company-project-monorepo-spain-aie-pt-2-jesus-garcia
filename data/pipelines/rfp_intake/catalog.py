"""Catálogo cerrado de departamentos y servicios de TrackFlow.

El catálogo es la fuente única de verdad para la Parte 1 del Hito 9: los
identificadores, responsables y servicios coinciden exactamente con el
``company-briefing.md``. Ningún agente puede inventar un departamento fuera de
este mapa; lo que no encaje se registra como servicio fuera de alcance.
"""

from __future__ import annotations

import re
from typing import Final

SERVICES: Final[dict[str, dict]] = {
    "warehousing": {
        "department_id": "warehouse",
        "label": "Almacenamiento",
        "aliases": (
            "warehousing",
            "warehouse",
            "almacenamiento",
            "almacenaje",
            "fulfillment",
            "fulfilment",
            "logística de almacén",
            "logistica de almacen",
            "picking",
            "packing",
            "stock",
        ),
    },
    "last_mile": {
        "department_id": "lastmile",
        "label": "Última milla",
        "aliases": (
            "last mile",
            "last-mile",
            "última milla",
            "ultima milla",
            "shipping",
            "envío",
            "envio",
            "envíos",
            "envios",
            "delivery",
            "entrega",
            "carrier",
            "transportista",
            "transportistas",
            "carrier selection",
        ),
    },
    "reverse_logistics": {
        "department_id": "reverse",
        "label": "Logística inversa",
        "aliases": (
            "reverse logistics",
            "reverse",
            "devoluciones",
            "devolución",
            "devolucion",
            "returns",
            "retornos",
            "logística inversa",
            "logistica inversa",
        ),
    },
}

DEPARTMENTS: Final[dict[str, dict]] = {
    "warehouse": {
        "label": "Warehouse Operations",
        "responsible": "Ana Whitfield",
        "service_id": "warehousing",
        "next_step": (
            "Pedir a Ana Whitfield capacidad disponible, coste por pallet/SKU, "
            "tiempo de onboarding y requisitos de integración."
        ),
        "requires": (
            "volumen mensual de pedidos o de SKUs, y capacidad necesaria",
        ),
    },
    "lastmile": {
        "label": "Last Mile and Carrier Management",
        "responsible": "Carlos Vega",
        "service_id": "last_mile",
        "next_step": (
            "Pedir a Carlos Vega coste por envío, transportistas disponibles "
            "según destino y SLA de entrega comprometido."
        ),
        "requires": (
            "volumen mensual de envíos y país/regiones de destino",
        ),
    },
    "reverse": {
        "label": "Reverse Logistics",
        "responsible": "Sofía Ramos",
        "service_id": "reverse_logistics",
        "next_step": (
            "Pedir a Sofía Ramos coste y tiempo de procesamiento de devoluciones; "
            "el mínimo permitido es 48 horas."
        ),
        "requires": (
            "volumen o tasa de devoluciones y condiciones de inspección",
        ),
    },
}

DEPARTMENT_ORDER: Final[tuple[str, ...]] = ("warehouse", "lastmile", "reverse")

SALES_OWNER: Final[str] = "Miguel Torres"

COUNTRY_CURRENCY: Final[dict[str, str]] = {
    "US": "USD",
    "Spain": "EUR",
}

COUNTRY_ALIASES: Final[dict[str, str]] = {
    "us": "US",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "united states": "US",
    "united states of america": "US",
    "estados unidos": "US",
    "eeuu": "US",
    "ee. uu.": "US",
    "ee uu": "US",
    "los angeles": "US",
    "california": "US",
    "la": "US",
    "spain": "Spain",
    "españa": "Spain",
    "espana": "Spain",
    "es": "Spain",
    "zaragoza": "Spain",
    "madrid": "Spain",
}

DEPARTMENT_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "warehouse": (
        "almacén",
        "almacen",
        "warehouse",
        "warehousing",
        "sku",
        "skus",
        "pallet",
        "pallets",
        "picking",
        "packing",
        "fulfillment",
        "fulfilment",
        "capacidad",
        "onboarding",
        "inventario",
        "stock",
        "erp",
    ),
    "lastmile": (
        "última milla",
        "ultima milla",
        "last mile",
        "envío",
        "envio",
        "envíos",
        "envios",
        "shipping",
        "delivery",
        "entrega",
        "carrier",
        "transportista",
        "transportistas",
        "sla",
        "destino",
        "tracking",
    ),
    "reverse": (
        "devolución",
        "devolucion",
        "devoluciones",
        "returns",
        "return",
        "reverse",
        "logística inversa",
        "logistica inversa",
        "inspección",
        "inspeccion",
        "reacondicionamiento",
        "restock",
        "retorno",
    ),
}

_ACCENT_RE = re.compile(r"[\u0300-\u036f]")


def normalize_text(value: str) -> str:
    """Minúsculas y sin acentos, para comparar alias y keywords."""

    lowered = (value or "").lower().strip()
    return _ACCENT_RE.sub("", lowered)


def normalize_country(value: object) -> str | None:
    """Devuelve ``US``, ``Spain`` o ``None``. Nunca adivina un país."""

    if not isinstance(value, str):
        return None
    key = normalize_text(value)
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    for alias, country in COUNTRY_ALIASES.items():
        if alias and re.search(rf"\b{re.escape(alias)}\b", key):
            return country
    return None


def currency_for_country(country: str | None) -> str | None:
    return COUNTRY_CURRENCY.get(country or "")


def normalize_service(value: str) -> str | None:
    """Mapea un servicio libre al identificador canónico del briefing."""

    key = normalize_text(value)
    if not key:
        return None
    for service_id, spec in SERVICES.items():
        if key == service_id:
            return service_id
        for alias in spec["aliases"]:
            alias_key = normalize_text(alias)
            if key == alias_key:
                return service_id
    return None


def normalize_services(values: object) -> tuple[list[str], list[str]]:
    """Devuelve ``(canónicos, desconocidos)`` sin perder los no reconocidos."""

    if not isinstance(values, list):
        return [], []
    canonical: list[str] = []
    unknown: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        service_id = normalize_service(value)
        if service_id is None:
            unknown.append(value.strip())
        elif service_id not in canonical:
            canonical.append(service_id)
    return canonical, unknown


def departments_for_services(services: list[str]) -> list[str]:
    """Traduce servicios canónicos a departamentos, en orden estable."""

    active: set[str] = set()
    for service_id in services:
        spec = SERVICES.get(service_id)
        if spec:
            active.add(spec["department_id"])
    return [department for department in DEPARTMENT_ORDER if department in active]


def department_spec(department_id: str) -> dict:
    try:
        return DEPARTMENTS[department_id]
    except KeyError as exc:  # pragma: no cover - defensa ante datos corruptos
        raise ValueError(f"Departamento desconocido: {department_id}") from exc


def is_known_department(department_id: object) -> bool:
    return isinstance(department_id, str) and department_id in DEPARTMENTS


def required_figures(department_id: str, metadata: dict) -> list[str]:
    """Preguntas abiertas por cifras imprescindibles que faltan en la RFP.

    Los workers no estiman nunca: si la RFP no declara la cifra, la pregunta
    viaja al resumen de Ventas.
    """

    questions: list[str] = []
    if department_id == "warehouse":
        if metadata.get("monthly_volume") is None:
            questions.append(
                "Falta el volumen mensual de pedidos: confirmarlo con el cliente "
                "antes de cotizar capacidad y coste por pedido."
            )
        if not metadata.get("sku_count"):
            questions.append(
                "Falta el número de SKUs a almacenar: confirmarlo para calcular "
                "ubicaciones y coste por SKU."
            )
    elif department_id == "lastmile":
        if metadata.get("monthly_volume") is None:
            questions.append(
                "Falta el volumen mensual de envíos: confirmarlo para cotizar "
                "coste por envío y capacidad de los transportistas."
            )
        if not metadata.get("client_country"):
            questions.append(
                "Falta el país/región de destino: confirmarlo para elegir "
                "transportistas y moneda."
            )
    elif department_id == "reverse":
        if not metadata.get("return_volume") and not metadata.get("return_rate"):
            questions.append(
                "Falta el volumen o la tasa de devoluciones: confirmarlo para "
                "dimensionar inspección y reacondicionamiento."
            )
    return questions


def scope_questions(metadata: dict, unknown_services: list[str]) -> list[str]:
    """Preguntas transversales para Ventas (no las inventa ningún worker)."""

    questions: list[str] = []
    if unknown_services:
        questions.append(
            "La RFP menciona servicios fuera del catálogo de TrackFlow "
            f"({', '.join(unknown_services)}): confirmar con el cliente si son "
            "imprescindibles y quién los cubriría."
        )
    if metadata.get("monthly_volume") is None:
        questions.append(
            "Solicitar al cliente el volumen mensual de pedidos (dato necesario "
            "para almacenamiento y última milla)."
        )
    if not metadata.get("budget_range"):
        questions.append(
            "La RFP no incluye presupuesto de referencia: pedirlo para calibrar "
            "la propuesta comercial."
        )
    if not metadata.get("deadline"):
        questions.append(
            "La RFP no fija una fecha límite clara: confirmar plazo de propuesta "
            "y fecha de go-live."
        )
    if not metadata.get("client_country"):
        questions.append(
            "Confirmar el país del cliente: determina la moneda (US → USD, "
            "España → EUR)."
        )
    return questions

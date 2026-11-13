"""Clasificador determinista de intención: RAG, tickets, inventario o ambos.

El agente decide a partir del contenido de la pregunta, sin que el usuario
tenga que indicar la fuente. Las reglas son deliberadamente conservadoras:
ante la duda se usa el RAG, y una pregunta con señal de ticket/SKU más un
término de política se resuelve con la tool **y** el RAG (``+rag``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

Route = Literal["rag", "incident", "inventory", "incident+rag", "inventory+rag"]
Warehouse = Literal["los_angeles", "zaragoza"]

INCIDENT_TERMS = (
    "ticket",
    "tickets",
    "incidencia",
    "incidencias",
    "incident",
    "incidents",
    "averia",
    "averias",
)

INVENTORY_TERMS = (
    "stock",
    "inventario",
    "inventory",
    "existencias",
    "existencia",
    "unidades",
    "sku",
    "skus",
    "disponibilidad",
    "disponible",
    "disponibles",
    "almacen",
    "almacenes",
)

POLICY_TERMS = (
    "politica",
    "politicas",
    "procedimiento",
    "procedimientos",
    "sla",
    "slas",
    "plazo",
    "plazos",
    "devolucion",
    "devoluciones",
    "devolver",
    "garantia",
    "garantias",
    "tarifa",
    "tarifas",
    "precio",
    "precios",
    "descuento",
    "descuentos",
    "transportista",
    "transportistas",
    "almacenamiento",
    "aprobacion",
    "condiciones",
    "reembolso",
    "reembolsos",
    "recogida",
    "contrato",
    "contratos",
)

STATUS_TERMS: dict[str, str] = {
    "abierto": "open",
    "abiertos": "open",
    "abierta": "open",
    "abiertas": "open",
    "en curso": "in_progress",
    "en progreso": "in_progress",
    "in progress": "in_progress",
    "resuelto": "resolved",
    "resueltos": "resolved",
    "resuelta": "resolved",
    "resueltas": "resolved",
    "descartado": "discarded",
    "descartados": "discarded",
    "descartada": "discarded",
    "descartadas": "discarded",
}

CATEGORY_TERMS: dict[str, str] = {
    "paquete perdido": "lost_parcel",
    "paquetes perdidos": "lost_parcel",
    "fallo de entrega": "delivery_failure",
    "fallos de entrega": "delivery_failure",
    "discrepancia de inventario": "inventory_discrepancy",
    "discrepancias de inventario": "inventory_discrepancy",
    "incidencia de transportista": "carrier_issue",
    "incidencias de transportista": "carrier_issue",
    "problema de transportista": "carrier_issue",
    "problemas de transportista": "carrier_issue",
    "incidencia de devolucion": "returns_issue",
    "incidencias de devolucion": "returns_issue",
    "incidencia de almacen": "warehouse_incident",
    "incidencias de almacen": "warehouse_incident",
    "fallo del sistema": "system_failure",
    "fallos del sistema": "system_failure",
    "queja de cliente": "client_complaint",
    "quejas de cliente": "client_complaint",
}

WAREHOUSE_TERMS: dict[str, Warehouse] = {
    "los angeles": "los_angeles",
    "zaragoza": "zaragoza",
}

TICKET_ID_RE = re.compile(
    r"(?:ticket|incidencia|incident|caso)\s*"
    r"(?:n[º°o.]*|id|numero|número)?\s*[-:#]?\s*(\d{1,9})",
    re.IGNORECASE,
)
HASH_ID_RE = re.compile(r"#\s*(\d{1,9})")
SKU_CODE_RE = re.compile(
    r"\b(?=[A-Za-z0-9-]*\d)[A-Za-z]{2,}[A-Za-z0-9]*(?:-[A-Za-z0-9]+){1,}\b"
)
PRODUCT_AFTER_DE_RE = re.compile(
    r"(?:stock|inventario|existencias|disponibilidad)\s+(?:de|del)\s+"
    r"([^?.,;\n]+)",
    re.IGNORECASE,
)
PRODUCT_AFTER_PARA_RE = re.compile(
    r"(?:stock|inventario|existencias|disponibilidad)\s+(?:para|en)\s+"
    r"([^?.,;\n]+)",
    re.IGNORECASE,
)
QUOTED_RE = re.compile(r"[\"'«»“”]([^\"'«»“”]{2,120})[\"'«»“”]")


class RoutingDecision(BaseModel):
    """Decisión de enrutado y argumentos extraídos de la pregunta."""

    route: Route
    ticket_id: int | None = None
    sku_code: str | None = None
    product_name: str | None = None
    warehouse: Warehouse | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    reason: str = ""
    source: Literal["rules"] = "rules"


def _normalize(text: str) -> str:
    """Minúsculas y sin acentos, para comparar términos de forma robusta."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return without_accents.lower()


def _contains(normalized: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized)
        for term in terms
    )


def _first_term(normalized: str, terms: dict[str, str]) -> str | None:
    for term, value in terms.items():
        if _contains(normalized, (term,)):
            return value
    return None


def _extract_ticket_id(text: str, normalized: str) -> int | None:
    match = TICKET_ID_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None
    if _contains(normalized, INCIDENT_TERMS):
        match = HASH_ID_RE.search(text)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


def _extract_sku_code(text: str) -> str | None:
    match = SKU_CODE_RE.search(text)
    return match.group(0).upper() if match else None


def _clean_product_name(value: str) -> str | None:
    candidate = value.strip().strip(" \"'«»“”")
    candidate = re.sub(
        r"^(?:el|la|los|las|un|una|unos|unas|producto|productos|"
        r"articulo|articulos|sku)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\s+(?:en|de)\s+(?:los\s+angeles|zaragoza)\s*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = candidate.strip().strip(" \"'«»“”")
    if not candidate or len(candidate) > 120:
        return None
    if _normalize(candidate) in WAREHOUSE_TERMS:
        return None
    return candidate


def _extract_product_name(text: str) -> str | None:
    for pattern in (PRODUCT_AFTER_DE_RE, PRODUCT_AFTER_PARA_RE):
        match = pattern.search(text)
        if match:
            candidate = _clean_product_name(match.group(1))
            if candidate:
                return candidate
    match = QUOTED_RE.search(text)
    if match:
        return _clean_product_name(match.group(1))
    return None


def _extract_warehouse(normalized: str) -> Warehouse | None:
    for term, value in WAREHOUSE_TERMS.items():
        if _contains(normalized, (term,)):
            return value
    return None


def _extract_incident_filters(normalized: str) -> dict[str, str]:
    filters: dict[str, str] = {}
    status = _first_term(normalized, STATUS_TERMS)
    if status:
        filters["status"] = status
    category = _first_term(normalized, CATEGORY_TERMS)
    if category:
        filters["category"] = category
    return filters


def classify_question(question: str) -> RoutingDecision:
    """Decide la fuente (o fuentes) que necesita la pregunta."""
    text = (question or "").strip()
    if not text:
        return RoutingDecision(
            route="rag",
            reason="Pregunta vacía; receive_question la rechazará.",
        )

    normalized = _normalize(text)
    ticket_id = _extract_ticket_id(text, normalized)
    has_incident_term = _contains(normalized, INCIDENT_TERMS)
    is_incident = has_incident_term or ticket_id is not None
    is_inventory = _contains(normalized, INVENTORY_TERMS)
    has_policy = _contains(normalized, POLICY_TERMS)

    if is_incident and is_inventory and ticket_id is None:
        # Desempate: un SKU explícito pesa más; si no, la señal de ticket.
        if _extract_sku_code(text):
            is_incident = False
        else:
            is_inventory = False

    if is_incident:
        filters = _extract_incident_filters(normalized)
        route: Route = "incident+rag" if has_policy else "incident"
        signals = ["término de ticket" if has_incident_term else "ID de ticket"]
        if ticket_id is not None:
            signals.append(f"ticket_id={ticket_id}")
        if filters:
            signals.append(f"filtros={filters}")
        if has_policy:
            signals.append("término de política")
        return RoutingDecision(
            route=route,
            ticket_id=ticket_id,
            filters=filters,
            reason="; ".join(signals),
        )

    if is_inventory:
        sku_code = _extract_sku_code(text)
        product_name = None if sku_code else _extract_product_name(text)
        warehouse = _extract_warehouse(normalized)
        route = "inventory+rag" if has_policy else "inventory"
        signals = ["término de inventario"]
        if sku_code:
            signals.append(f"sku_code={sku_code}")
        if product_name:
            signals.append(f"producto={product_name}")
        if warehouse:
            signals.append(f"almacén={warehouse}")
        if has_policy:
            signals.append("término de política")
        return RoutingDecision(
            route=route,
            sku_code=sku_code,
            product_name=product_name,
            warehouse=warehouse,
            reason="; ".join(signals),
        )

    return RoutingDecision(
        route="rag",
        reason=(
            "Sin señales de ticket ni inventario; se consulta la base de "
            "conocimiento."
        ),
    )


__all__ = [
    "CATEGORY_TERMS",
    "INCIDENT_TERMS",
    "INVENTORY_TERMS",
    "POLICY_TERMS",
    "Route",
    "RoutingDecision",
    "STATUS_TERMS",
    "WAREHOUSE_TERMS",
    "classify_question",
]

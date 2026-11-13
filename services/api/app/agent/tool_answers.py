"""Respuestas deterministas a partir de los resultados de las tools.

Estas respuestas no pasan por el LLM: si la tool no puede confirmar un dato,
el agente lo dice con honestidad en lugar de inventar un estado o un stock.
"""

from __future__ import annotations

from typing import Any

STATUS_LABELS = {
    "open": "Abierto",
    "in_progress": "En curso",
    "resolved": "Resuelto",
    "discarded": "Descartado",
}

CATEGORY_LABELS = {
    "lost_parcel": "Paquete perdido",
    "delivery_failure": "Fallo de entrega",
    "inventory_discrepancy": "Discrepancia de inventario",
    "carrier_issue": "Incidencia de transportista",
    "returns_issue": "Incidencia de devolución",
    "warehouse_incident": "Incidencia de almacén",
    "system_failure": "Fallo del sistema",
    "client_complaint": "Queja de cliente",
    "other": "Otra",
}

ORIGIN_LABELS = {
    "customer": "Cliente",
    "branch": "Sede",
    "internal": "Interno",
}

BRANCH_LABELS = {
    "central": "Central",
    "la_warehouse": "Almacén de Los Ángeles",
    "la_office": "Oficina de Los Ángeles",
    "zaragoza_warehouse": "Almacén de Zaragoza",
    "zaragoza_office": "Oficina de Zaragoza",
}

WAREHOUSE_LABELS = {
    "los_angeles": "Los Ángeles",
    "zaragoza": "Zaragoza",
}

INCIDENT_NO_CONFIRM = (
    "No pude confirmar el estado de ese ticket ahora mismo"
)
INVENTORY_NO_CONFIRM = (
    "No pude confirmar el stock de ese producto ahora mismo"
)


def _label(labels: dict[str, str], value: Any) -> str:
    text = str(value or "")
    return labels.get(text, text or "No especificado")


def _incident_error_message(result: dict) -> str | None:
    error = result.get("error")
    if error == "timeout":
        return (
            f"{INCIDENT_NO_CONFIRM}: el gestor de incidencias no respondió a "
            "tiempo. Inténtalo de nuevo en unos minutos."
        )
    if error == "unavailable":
        return (
            f"{INCIDENT_NO_CONFIRM}: el gestor de incidencias no está "
            "disponible en este momento. Inténtalo de nuevo en unos minutos."
        )
    if error == "forbidden":
        return (
            "No tengo permisos para consultar los detalles de ese ticket con "
            "tu rol actual. Contacta con un responsable de operaciones."
        )
    if error == "invalid_input":
        return (
            "Para consultar un ticket necesito su número de ID (por ejemplo, "
            "«ticket 482») o un filtro de búsqueda (estado, categoría, origen "
            "o sede)."
        )
    if error == "not_found":
        return result.get("message") or (
            "No encontré ningún ticket que coincida con la consulta. No puedo "
            "confirmar su estado; verifica el número o los filtros."
        )
    return None


def format_incident_answer(result: dict) -> str:
    """Respuesta legible para una consulta de tickets."""
    error_message = _incident_error_message(result)
    if error_message:
        return error_message

    incidents = result.get("incidents") or []
    if not incidents:
        return (
            "No encontré ningún ticket que coincida con la consulta. No puedo "
            "confirmar su estado; verifica el número o los filtros."
        )

    if len(incidents) == 1:
        incident = incidents[0]
        lines = [
            (
                f"El ticket {incident.get('id')} está en estado "
                f"«{_label(STATUS_LABELS, incident.get('status'))}» "
                f"({incident.get('status')})."
            ),
            f"- Título: {incident.get('title') or 'Sin título'}",
            (
                f"- Categoría: {_label(CATEGORY_LABELS, incident.get('category'))} "
                f"({incident.get('category')})"
            ),
            (
                f"- Origen: {_label(ORIGIN_LABELS, incident.get('origin'))} "
                f"({incident.get('origin')})"
            ),
            (
                f"- Sede: {_label(BRANCH_LABELS, incident.get('branch'))} "
                f"({incident.get('branch')})"
            ),
        ]
        if incident.get("created_at"):
            lines.append(f"- Creado: {incident['created_at']}")
        if incident.get("updated_at"):
            lines.append(f"- Actualizado: {incident['updated_at']}")
        return "\n".join(lines)

    lines = [f"Encontré {len(incidents)} tickets que coinciden con la consulta:"]
    for incident in incidents:
        lines.append(
            f"- Ticket {incident.get('id')}: "
            f"«{_label(STATUS_LABELS, incident.get('status'))}» — "
            f"{incident.get('title') or 'Sin título'} "
            f"({_label(CATEGORY_LABELS, incident.get('category'))})"
        )
    return "\n".join(lines)


def _inventory_error_message(result: dict) -> str | None:
    error = result.get("error")
    if error == "timeout":
        return (
            f"{INVENTORY_NO_CONFIRM}: el servicio de inventario no respondió a "
            "tiempo. Inténtalo de nuevo en unos minutos."
        )
    if error == "unavailable":
        return (
            f"{INVENTORY_NO_CONFIRM}: el servicio de inventario no está "
            "disponible en este momento. Inténtalo de nuevo en unos minutos."
        )
    if error == "invalid_input":
        return (
            "Para consultar stock necesito el SKU o el nombre del producto "
            "(por ejemplo, «CLT-SNK-W-42» o «zapatillas blancas»)."
        )
    if error == "not_found":
        return result.get("message") or (
            "No tengo constancia de stock para ese producto en el inventario."
        )
    return None


def _stock_detail(item: dict) -> str:
    by_warehouse = item.get("current_stock_by_warehouse") or {}
    if not isinstance(by_warehouse, dict) or not by_warehouse:
        return ""
    parts = [
        f"{WAREHOUSE_LABELS.get(str(warehouse), str(warehouse))}: {quantity}"
        for warehouse, quantity in by_warehouse.items()
    ]
    return ", ".join(parts)


def format_inventory_answer(result: dict) -> str:
    """Respuesta legible para una consulta de stock."""
    error_message = _inventory_error_message(result)
    if error_message:
        return error_message

    items = result.get("items") or []
    if not items:
        return (
            "No tengo constancia de stock para ese producto en el inventario. "
            "Verifica el SKU o el nombre del producto."
        )

    if len(items) == 1:
        item = items[0]
        detail = _stock_detail(item)
        total = item.get("current_stock", 0)
        suffix = f" ({detail})" if detail else ""
        if total <= 0:
            return (
                f"No hay unidades disponibles de «{item.get('name')}» "
                f"({item.get('sku_code')}). Stock actual: 0{suffix}."
            )
        return (
            f"Sí, hay stock de «{item.get('name')}» ({item.get('sku_code')}): "
            f"{total} unidades en total{suffix}."
        )

    lines = [f"Encontré {len(items)} productos que coinciden con la consulta:"]
    for item in items:
        detail = _stock_detail(item)
        suffix = f" ({detail})" if detail else ""
        lines.append(
            f"- {item.get('name')} ({item.get('sku_code')}): "
            f"{item.get('current_stock', 0)} unidades{suffix}"
        )
    return "\n".join(lines)


def format_tool_context(
    tool_name: str | None,
    result: dict | None,
) -> dict | None:
    """Convierte el resultado de una tool en un bloque de contexto para el LLM.

    Se usa en la ruta ``+rag``: el LLM recibe los hechos en tiempo real junto
    con los chunks recuperados y puede combinarlos sin inventar datos.
    """
    if not tool_name:
        return None

    if tool_name == "incident_lookup":
        text = format_incident_answer(result or {})
        source_document = "incident-manager"
        section = "Consulta de ticket en tiempo real"
    elif tool_name == "inventory_lookup":
        text = format_inventory_answer(result or {})
        source_document = "inventory-api"
        section = "Consulta de stock en tiempo real"
    else:
        return None

    if not text.strip():
        return None

    return {
        "company": "trackflow",
        "source_document": source_document,
        "section": section,
        "chunk_index": 0,
        "text": text,
    }


__all__ = [
    "BRANCH_LABELS",
    "CATEGORY_LABELS",
    "INCIDENT_NO_CONFIRM",
    "INVENTORY_NO_CONFIRM",
    "ORIGIN_LABELS",
    "STATUS_LABELS",
    "WAREHOUSE_LABELS",
    "format_incident_answer",
    "format_inventory_answer",
    "format_tool_context",
]

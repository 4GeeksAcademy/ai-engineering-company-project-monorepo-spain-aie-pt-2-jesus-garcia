"""Eventos de dominio del canal en tiempo real.

Los nombres y campos reutilizan las entidades ya definidas en el sistema de
RFPs (``ticket_id``, ``rfp_id``, ``client_name``, ``client_country``,
``services_requested``, ``status``, ``created_at``) y la regla de SLA del
briefing. No hay ningún sobre ``{"event", "data"}``: el nombre viaja en la
línea ``event:`` y ``data:`` lleva solo campos de la entidad.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from .broker import Event, get_broker

logger = logging.getLogger(__name__)

RFP_TICKET_CREATED = "rfp_ticket_created"
RFP_TICKET_METADATA_READY = "rfp_ticket_metadata_ready"
SLA_THRESHOLD_ALERT = "sla_threshold_alert"
STREAM_LAGGED = "stream_lagged"


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def rfp_ticket_payload(ticket, metadata=None) -> dict[str, Any]:
    """Payload del ticket con los campos del briefing.

    En el momento del registro (``status=analizando``) los metadatos de la RFP
    todavía no existen: viajan como ``null``/``[]`` hasta que el pipeline
    confirma que es una RFP válida y emite ``rfp_ticket_metadata_ready``.
    """

    return {
        "ticket_id": ticket.id,
        "rfp_id": ticket.rfp_id,
        "client_name": getattr(metadata, "client_name", None),
        "client_country": getattr(metadata, "client_country", None),
        "services_requested": list(
            getattr(metadata, "services_requested", None) or []
        ),
        "currency": getattr(metadata, "currency", None),
        "status": ticket.status,
        "created_at": _iso(ticket.created_at),
        "original_filename": ticket.original_filename,
        "pipeline_stage": ticket.pipeline_stage,
    }


def publish_event(name: str, data: dict[str, Any]) -> Event | None:
    """Publica en el bus; una caída del canal nunca rompe la petición."""

    try:
        return get_broker().publish(name, data)
    except Exception:  # pragma: no cover - Redis caído, etc.
        logger.exception("No se pudo publicar el evento %s", name)
        return None


def publish_rfp_ticket_created(ticket, metadata=None) -> Event | None:
    return publish_event(
        RFP_TICKET_CREATED, rfp_ticket_payload(ticket, metadata)
    )


def publish_rfp_ticket_metadata_ready(ticket, metadata) -> Event | None:
    return publish_event(
        RFP_TICKET_METADATA_READY, rfp_ticket_payload(ticket, metadata)
    )

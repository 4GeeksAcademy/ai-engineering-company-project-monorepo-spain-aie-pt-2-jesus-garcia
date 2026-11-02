import logging
from datetime import datetime, timezone
from uuid import uuid4

from models import TELEMETRY_SCHEMA_VERSION, TelemetryEvent, TelemetrySource

logger = logging.getLogger("api.telemetry.emit")


def build_event(
    event_type: str,
    properties: dict,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    app: str = "backoffice",
) -> TelemetryEvent | None:
    """Construye y valida el envelope sin persistir ni loguear.

    La capa de inventario lo usa para escribir el evento en el outbox dentro de
    la misma transacción que la orden.
    """

    try:
        return TelemetryEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id or "backend",
            user_id=user_id,
            event_type=event_type,
            schema_version=TELEMETRY_SCHEMA_VERSION,
            request_id=request_id,
            source=TelemetrySource.backend,
            app=app,
            properties={key: value for key, value in properties.items() if value is not None},
        )
    except Exception:
        logger.exception("No se pudo construir el evento de telemetría %s", event_type)
        return None


def log_event(event: TelemetryEvent) -> None:
    logger.info(
        "Telemetry event emitted: %s | app=%s | properties=%s",
        event.event_type.value,
        event.app.value,
        event.properties,
    )


def emit_event(
    event_type: str,
    properties: dict,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    app: str = "backoffice",
) -> TelemetryEvent | None:
    """Compatibilidad: construye y loguea (sin persistir)."""

    event = build_event(
        event_type,
        properties,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        app=app,
    )
    if event is not None:
        log_event(event)
    return event

"""Notificaciones de operación (webhook opcional).

Sin ``PIPELINE_ALERT_WEBHOOK`` solo se escribe en el log: el pipeline nunca
falla porque el canal de alertas esté caído.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("pipeline.alerts")


def send_alert(
    subject: str,
    message: str,
    *,
    level: str = "error",
    webhook: str | None = None,
) -> bool:
    """Envía una alerta al webhook configurado; devuelve si se entregó."""

    target = webhook or os.getenv("PIPELINE_ALERT_WEBHOOK", "").strip()
    text = f"[{level.upper()}] {subject}\n{message}"
    if not target:
        logger.warning("Alerta sin webhook configurado: %s", text)
        return False

    try:
        response = httpx.post(target, json={"text": text}, timeout=5.0)
        response.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 - una alerta no debe tumbar el pipeline
        logger.exception("No se pudo enviar la alerta: %s", subject)
        return False

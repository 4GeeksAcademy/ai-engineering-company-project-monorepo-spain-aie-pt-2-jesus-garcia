"""Configuración del pipeline (variables de entorno y constantes de negocio)."""

from __future__ import annotations

from datetime import date
import os

from dotenv import load_dotenv

load_dotenv()

PIPELINE_NAME = "weekly_warehouse_client_performance"
PIPELINE_VERSION = "0.1.0"

#: Eventos obligatorios del briefing. No se amplía el alcance en v1.
EVENT_TYPES: tuple[str, ...] = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "inventory_discrepancy_detected",
)

INBOUND = "inbound_order_created"
OUTBOUND = "outbound_order_created"
STOCKOUT = "stock_threshold_triggered"
DISCREPANCY = "inventory_discrepancy_detected"

WAREHOUSES: tuple[str, ...] = ("los_angeles", "zaragoza")

DEFAULT_LOOKBACK_WEEKS = int(os.getenv("PIPELINE_LOOKBACK_WEEKS", "3"))
REPORTING_SCHEMA = os.getenv("PIPELINE_REPORTING_SCHEMA", "reporting")
OPS_SCHEMA = os.getenv("PIPELINE_OPS_SCHEMA", "ops")

#: Umbral de tasa de rechazo (G9). En muestras pequeñas solo avisa.
REJECT_WARN_RATE = 0.01
REJECT_BLOCK_RATE = 0.05
REJECT_MIN_ROWS_FOR_BLOCK = 50


def get_database_url() -> str:
    """URL de la BD del pipeline.

    Se usa ``DATABASE_URL_PIPELINE`` para poder dar al pipeline un rol de solo
    lectura sobre ``telemetry_events``; ``DATABASE_URL`` es el fallback local.
    """

    url = os.getenv("DATABASE_URL_PIPELINE") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL_PIPELINE (o DATABASE_URL) para ejecutar el pipeline."
        )
    return url


def get_instrumentation_since() -> date | None:
    """Fecha desde la que quiebres y discrepancias están instrumentados.

    Antes de esa fecha los KPIs de stockout/discrepancia son 0 por ausencia de
    datos, no porque no ocurrieran. El gate G6 solo aplica a partir de aquí.
    """

    raw = os.getenv("PIPELINE_INSTRUMENTATION_SINCE", "").strip()
    return date.fromisoformat(raw) if raw else None

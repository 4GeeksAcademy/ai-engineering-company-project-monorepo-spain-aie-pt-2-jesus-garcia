"""Tools de lectura en tiempo real del agente.

Cada tool tiene una única responsabilidad y un contrato tipado:

* ``incident_lookup`` — estado y datos de tickets del gestor de incidencias.
* ``inventory_lookup`` — stock actual por producto y almacén.

Ambas son de solo lectura, in-process y con timeout/fallback controlados.
"""

from __future__ import annotations

from .contracts import (
    IncidentLookup,
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
    InventoryItem,
    InventoryLookup,
    InventoryLookupInput,
    InventoryLookupOutput,
)
from .execution import (
    DEFAULT_INCIDENT_TIMEOUT_SECONDS,
    DEFAULT_INVENTORY_TIMEOUT_SECONDS,
    ToolTimeout,
    call_with_timeout,
    incident_timeout_seconds,
    inventory_timeout_seconds,
)
from .incidents import TOOL_NAME as INCIDENT_TOOL_NAME
from .incidents import lookup_incident
from .inventory import TOOL_NAME as INVENTORY_TOOL_NAME
from .inventory import lookup_inventory

__all__ = [
    "DEFAULT_INCIDENT_TIMEOUT_SECONDS",
    "DEFAULT_INVENTORY_TIMEOUT_SECONDS",
    "INCIDENT_TOOL_NAME",
    "INVENTORY_TOOL_NAME",
    "IncidentLookup",
    "IncidentLookupInput",
    "IncidentLookupOutput",
    "IncidentRecord",
    "InventoryItem",
    "InventoryLookup",
    "InventoryLookupInput",
    "InventoryLookupOutput",
    "ToolTimeout",
    "call_with_timeout",
    "incident_timeout_seconds",
    "inventory_timeout_seconds",
    "lookup_incident",
    "lookup_inventory",
]

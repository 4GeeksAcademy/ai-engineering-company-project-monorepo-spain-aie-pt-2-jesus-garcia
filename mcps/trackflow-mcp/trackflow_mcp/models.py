"""Contratos de entrada/salida de las tools del MCP Server.

Los valores de los enums y los nombres de campo espejan exactamente los modelos
de ``services/api`` (``models.py`` y ``schemas.py``). FastMCP genera el
``inputSchema`` de cada tool a partir de sus parámetros tipados y el
``outputSchema`` a partir de estos modelos.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IncidentStatus = Literal["open", "in_progress", "resolved", "discarded"]
IncidentOrigin = Literal["customer", "branch", "internal"]
IncidentBranch = Literal[
    "central",
    "la_warehouse",
    "la_office",
    "zaragoza_warehouse",
    "zaragoza_office",
]
IncidentCategory = Literal[
    "lost_parcel",
    "delivery_failure",
    "inventory_discrepancy",
    "carrier_issue",
    "returns_issue",
    "warehouse_incident",
    "system_failure",
    "client_complaint",
    "other",
]
Warehouse = Literal["los_angeles", "zaragoza"]
StockOperation = Literal["inbound", "outbound"]


class IncidentRecord(BaseModel):
    """Incidencia tal y como la expone el Incidents Manager."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="ID de la incidencia (campo `id` de la API).")
    title: str
    description: str | None = None
    description_excerpt: str | None = None
    origin: str
    branch: str
    category: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class IncidentQueryOutput(BaseModel):
    ok: bool = True
    found: bool
    incidents: list[IncidentRecord] = Field(default_factory=list)
    message: str = ""


class IncidentSummaryOutput(BaseModel):
    ok: bool = True
    by_status: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_origin: dict[str, int] = Field(default_factory=dict)
    by_branch: dict[str, int] = Field(default_factory=dict)


class IncidentMutationOutput(BaseModel):
    ok: bool = True
    incident: IncidentRecord


class InventoryItem(BaseModel):
    """Producto con stock calculado desde las órdenes (nunca un contador)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    sku_code: str
    warehouse: str
    client_id: str | None = None
    min_stock: int | None = None
    current_stock: int = 0
    current_stock_by_warehouse: dict[str, int] = Field(default_factory=dict)


class InventoryQueryOutput(BaseModel):
    ok: bool = True
    found: bool
    items: list[InventoryItem] = Field(default_factory=list)
    message: str = ""


class InventoryWriteRejected(BaseModel):
    ok: Literal[False] = False
    error_code: Literal["INVENTORY_READ_ONLY"] = "INVENTORY_READ_ONLY"
    message: str
    details: dict = Field(default_factory=dict)


__all__ = [
    "IncidentBranch",
    "IncidentCategory",
    "IncidentMutationOutput",
    "IncidentOrigin",
    "IncidentQueryOutput",
    "IncidentRecord",
    "IncidentStatus",
    "IncidentSummaryOutput",
    "InventoryItem",
    "InventoryQueryOutput",
    "InventoryWriteRejected",
    "StockOperation",
    "Warehouse",
]

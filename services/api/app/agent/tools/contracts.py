"""Contratos tipados de las tools del agente.

Los enums se declaran aquí de forma explícita para que el contrato de la tool
sea autocontenido y pueda importarse sin cargar los modelos ORM de la API
(``sqlmodel``/``sqlalchemy``). Los valores espejan las constantes de dominio de
``services/api/models.py``.
"""

from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
ToolError = Literal[
    "invalid_input",
    "not_found",
    "forbidden",
    "timeout",
    "unavailable",
]
Warehouse = Literal["los_angeles", "zaragoza"]


class IncidentLookupInput(BaseModel):
    """Entrada de la tool de tickets: un ID o filtros de búsqueda."""

    ticket_id: int | None = Field(
        default=None,
        ge=1,
        description="ID numérico del ticket/incidencia.",
    )
    status: IncidentStatus | None = None
    category: IncidentCategory | None = None
    origin: IncidentOrigin | None = None
    branch: IncidentBranch | None = None
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def _require_criterion(self) -> "IncidentLookupInput":
        if self.ticket_id is None and not any(
            (self.status, self.category, self.origin, self.branch)
        ):
            raise ValueError(
                "Indica ticket_id o al menos un filtro "
                "(status, category, origin o branch)."
            )
        return self


class IncidentRecord(BaseModel):
    """Campos que expone el gestor de incidencias para un ticket."""

    id: str
    title: str
    description: str | None = None
    description_excerpt: str | None = None
    origin: str
    branch: str
    category: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class IncidentLookupOutput(BaseModel):
    """Salida tipada: encontrado / no encontrado / error controlado."""

    ok: bool
    found: bool
    incidents: list[IncidentRecord] = Field(default_factory=list)
    error: ToolError | None = None
    message: str = ""


class InventoryLookupInput(BaseModel):
    """Entrada de la tool de inventario: un producto y, opcionalmente, almacén."""

    sku_id: int | None = Field(default=None, ge=1)
    sku_code: str | None = None
    name_query: str | None = None
    warehouse: Warehouse | None = None
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("sku_code", "name_query")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def _require_criterion(self) -> "InventoryLookupInput":
        if not any((self.sku_id, self.sku_code, self.name_query)):
            raise ValueError(
                "Indica sku_id, sku_code o name_query para consultar el stock."
            )
        return self


class InventoryItem(BaseModel):
    """Producto con su stock actual, calculado desde las órdenes."""

    id: int
    name: str
    sku_code: str
    warehouse: str
    client_id: str | None = None
    min_stock: int | None = None
    current_stock: int
    current_stock_by_warehouse: dict[str, int] = Field(default_factory=dict)


class InventoryLookupOutput(BaseModel):
    """Salida tipada de la consulta de stock."""

    ok: bool
    found: bool
    items: list[InventoryItem] = Field(default_factory=list)
    error: ToolError | None = None
    message: str = ""


IncidentLookup = Callable[[IncidentLookupInput], IncidentLookupOutput]
InventoryLookup = Callable[[InventoryLookupInput], InventoryLookupOutput]


__all__ = [
    "IncidentBranch",
    "IncidentCategory",
    "IncidentLookup",
    "IncidentLookupInput",
    "IncidentLookupOutput",
    "IncidentOrigin",
    "IncidentRecord",
    "IncidentStatus",
    "InventoryItem",
    "InventoryLookup",
    "InventoryLookupInput",
    "InventoryLookupOutput",
    "ToolError",
    "Warehouse",
]

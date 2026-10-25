from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    name: str
    sku_code: str
    warehouse: str


class SKURead(BaseModel):
    id: int
    name: str
    sku_code: str
    warehouse: str
    current_stock: int = 0
    current_stock_by_warehouse: dict[str, int] = {}


class StockEntryCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    warehouse: str


class StockEntryRead(BaseModel):
    id: int
    sku_id: int
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime


class StockExitCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    warehouse: str


class StockExitRead(BaseModel):
    id: int
    sku_id: int
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime


class InventoryOrderItem(BaseModel):
    id: int
    order_type: str
    sku_id: int
    product_name: str
    warehouse: str
    quantity: int
    user_email: str = ""
    created_at: datetime


class TelemetryBatch(BaseModel):
    """Envelope laxo: los eventos se validan individualmente en el handler.

    El body completo solo falla si `events` no es una lista; así un evento
    inválido no tumba el resto del lote.
    """

    events: list[Any] = Field(default_factory=list)


class TelemetryIngestResponse(BaseModel):
    received: int
    stored: int
    rejected: int
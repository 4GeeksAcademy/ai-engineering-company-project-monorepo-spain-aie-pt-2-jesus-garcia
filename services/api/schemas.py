from datetime import datetime

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
    user_uuid: str
    created_at: datetime
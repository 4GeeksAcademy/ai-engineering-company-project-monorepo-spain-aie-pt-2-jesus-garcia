from fastapi import HTTPException
from sqlmodel import Session, func, select

from models import SKU, StockEntry, StockExit
from schemas import StockEntryCreate, StockExitCreate

WAREHOUSES = ("los_angeles", "zaragoza")


def compute_stock(session: Session, sku_id: int, warehouse: str) -> int:
    inbound = session.exec(
        select(func.coalesce(func.sum(StockEntry.quantity), 0))
        .where(StockEntry.sku_id == sku_id, StockEntry.warehouse == warehouse)
    ).one()
    outbound = session.exec(
        select(func.coalesce(func.sum(StockExit.quantity), 0))
        .where(StockExit.sku_id == sku_id, StockExit.warehouse == warehouse)
    ).one()
    return inbound - outbound


def compute_stock_by_warehouse(session: Session, sku_id: int) -> dict[str, int]:
    return {wh: compute_stock(session, sku_id, wh) for wh in WAREHOUSES}


def _validate_order_input(session: Session, sku_id: int, quantity: int, warehouse: str) -> SKU:
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity debe ser un entero positivo.")
    if warehouse not in WAREHOUSES:
        raise HTTPException(
            status_code=400,
            detail=f"warehouse inválido. Debe ser uno de: {', '.join(WAREHOUSES)}.",
        )
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail=f"SKU {sku_id} no encontrado.")
    return sku


def create_inbound(session: Session, data: StockEntryCreate, user_uuid: str) -> StockEntry:
    _validate_order_input(session, data.sku_id, data.quantity, data.warehouse)
    entry = StockEntry(
        sku_id=data.sku_id,
        quantity=data.quantity,
        warehouse=data.warehouse,
        user_uuid=user_uuid,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def create_outbound(session: Session, data: StockExitCreate, user_uuid: str) -> StockExit:
    sku = _validate_order_input(session, data.sku_id, data.quantity, data.warehouse)
    available = compute_stock(session, data.sku_id, data.warehouse)
    if data.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Stock insuficiente para SKU '{sku.sku_code}'. "
                f"Disponible: {available}, solicitado: {data.quantity}."
            ),
        )
    exit_record = StockExit(
        sku_id=data.sku_id,
        quantity=data.quantity,
        warehouse=data.warehouse,
        user_uuid=user_uuid,
    )
    session.add(exit_record)
    session.commit()
    session.refresh(exit_record)
    return exit_record
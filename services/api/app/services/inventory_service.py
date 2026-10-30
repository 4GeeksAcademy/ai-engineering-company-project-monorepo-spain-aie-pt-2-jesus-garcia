from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.telemetry.emitter import build_event, emit_event
from app.telemetry.outbox import enqueue_event
from models import InventoryDiscrepancy, SKU, StockEntry, StockExit
from schemas import InventoryDiscrepancyCreate, StockEntryCreate, StockExitCreate

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


def _base_properties(sku: SKU, warehouse: str) -> dict:
    return {
        "warehouse": warehouse,
        "client_id": sku.client_id,
        "product_id": sku.sku_code,
    }


def create_inbound(session: Session, data: StockEntryCreate, user_uuid: str) -> StockEntry:
    sku = _validate_order_input(session, data.sku_id, data.quantity, data.warehouse)
    entry = StockEntry(
        sku_id=data.sku_id,
        quantity=data.quantity,
        warehouse=data.warehouse,
        user_uuid=user_uuid,
        client_id=sku.client_id,
    )
    session.add(entry)
    session.flush()

    event = build_event(
        "inbound_order_created",
        {
            **_base_properties(sku, data.warehouse),
            "quantity": data.quantity,
            "order_id": entry.id,
        },
        user_id=user_uuid,
    )
    enqueue_event(session, event)
    session.commit()
    session.refresh(entry)
    return entry


def create_outbound(session: Session, data: StockExitCreate, user_uuid: str) -> StockExit:
    sku = _validate_order_input(session, data.sku_id, data.quantity, data.warehouse)
    available = compute_stock(session, data.sku_id, data.warehouse)
    if data.quantity > available:
        emit_event(
            "outbound_rejected_insufficient_stock",
            {
                "warehouse": data.warehouse,
                "product_id": sku.sku_code,
                "requested_quantity": data.quantity,
                "available_quantity": available,
                "deficit": data.quantity - available,
            },
            user_id=user_uuid,
        )
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
        client_id=sku.client_id,
    )
    session.add(exit_record)
    session.flush()
    new_stock = compute_stock(session, data.sku_id, data.warehouse)

    event = build_event(
        "outbound_order_created",
        {
            **_base_properties(sku, data.warehouse),
            "quantity": data.quantity,
            "order_id": exit_record.id,
        },
        user_id=user_uuid,
    )
    enqueue_event(session, event)

    if (
        sku.min_stock is not None
        and available >= sku.min_stock
        and new_stock < sku.min_stock
    ):
        stockout = build_event(
            "stock_threshold_triggered",
            {
                **_base_properties(sku, data.warehouse),
                "quantity": new_stock,
                "min_stock": sku.min_stock,
                "deficit": sku.min_stock - new_stock,
            },
            user_id=user_uuid,
        )
        enqueue_event(session, stockout)

    session.commit()
    session.refresh(exit_record)
    return exit_record


def create_discrepancy(
    session: Session,
    data: InventoryDiscrepancyCreate,
    user_uuid: str,
) -> InventoryDiscrepancy:
    """Registra el detalle y emite como máximo un evento por ``order_id``."""

    if data.warehouse not in WAREHOUSES:
        raise HTTPException(
            status_code=400,
            detail=f"warehouse inválido. Debe ser uno de: {', '.join(WAREHOUSES)}.",
        )
    sku = session.get(SKU, data.sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail=f"SKU {data.sku_id} no encontrado.")

    existing = session.exec(
        select(InventoryDiscrepancy).where(
            InventoryDiscrepancy.order_id == data.order_id,
            InventoryDiscrepancy.sku_id == data.sku_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una discrepancia para ese pedido y SKU.",
        )

    delta = data.physical_quantity - data.system_quantity
    record = InventoryDiscrepancy(
        order_id=data.order_id,
        sku_id=data.sku_id,
        warehouse=data.warehouse,
        client_id=sku.client_id,
        system_quantity=data.system_quantity,
        physical_quantity=data.physical_quantity,
        discrepancy_delta=delta,
        incident_id=data.incident_id,
    )
    session.add(record)
    session.flush()

    count_for_order = int(
        session.exec(
            select(func.count())
            .select_from(InventoryDiscrepancy)
            .where(InventoryDiscrepancy.order_id == data.order_id)
        ).one()
        or 0
    )
    if count_for_order == 1:
        event = build_event(
            "inventory_discrepancy_detected",
            {
                **_base_properties(sku, data.warehouse),
                "quantity": abs(delta),
                "system_quantity": data.system_quantity,
                "physical_quantity": data.physical_quantity,
                "discrepancy_delta": delta,
                "detection_source": "manual_audit",
                "order_id": data.order_id,
                "incident_id": data.incident_id,
            },
            user_id=user_uuid,
        )
        enqueue_event(session, event)

    session.commit()
    session.refresh(record)
    return record

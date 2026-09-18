from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from database import get_db
from models import SKU, StockEntry, StockExit
from schemas import (
    InventoryOrderItem,
    SKUCreate,
    SKURead,
    StockEntryCreate,
    StockEntryRead,
    StockExitCreate,
    StockExitRead,
)
from app.core.dependencies import get_current_user, require_manager
from app.services.inventory_service import (
    compute_stock_by_warehouse,
    create_inbound,
    create_outbound,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _sku_to_read(sku: SKU, session: Session) -> SKURead:
    by_warehouse = compute_stock_by_warehouse(session, sku.id)
    return SKURead(
        id=sku.id,
        name=sku.name,
        sku_code=sku.sku_code,
        warehouse=sku.warehouse,
        current_stock=sum(by_warehouse.values()),
        current_stock_by_warehouse=by_warehouse,
    )


@router.get(
    "/products",
    response_model=list[SKURead],
    summary="Listar productos con stock actual por almacén",
)
def list_products(
    _=Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[SKURead]:
    skus = session.exec(select(SKU)).all()
    return [_sku_to_read(sku, session) for sku in skus]


@router.get(
    "/products/{product_id}",
    response_model=SKURead,
    summary="Obtener un producto con su stock actual",
)
def get_product(
    product_id: int,
    _=Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SKURead:
    sku = session.get(SKU, product_id)
    if sku is None:
        raise HTTPException(status_code=404, detail=f"SKU {product_id} no encontrado.")
    return _sku_to_read(sku, session)


@router.post(
    "/products",
    response_model=SKURead,
    status_code=201,
    summary="Crear un producto (empieza con stock cero)",
)
def create_product(
    payload: SKUCreate,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> SKURead:
    sku = SKU(
        name=payload.name,
        sku_code=payload.sku_code,
        warehouse=payload.warehouse,
    )
    session.add(sku)
    session.commit()
    session.refresh(sku)
    return _sku_to_read(sku, session)


@router.post(
    "/orders/inbound",
    response_model=StockEntryRead,
    status_code=201,
    summary="Registrar una orden inbound (entrada de stock)",
)
def create_inbound_order(
    payload: StockEntryCreate,
    current_user: dict = Depends(require_manager),
    session: Session = Depends(get_db),
) -> StockEntryRead:
    entry = create_inbound(session, payload, str(current_user["id"]))
    return StockEntryRead(
        id=entry.id,
        sku_id=entry.sku_id,
        quantity=entry.quantity,
        warehouse=entry.warehouse,
        user_uuid=entry.user_uuid,
        created_at=entry.created_at,
    )


@router.post(
    "/orders/outbound",
    response_model=StockExitRead,
    status_code=201,
    summary="Registrar una orden outbound (salida de stock, check-then-write)",
)
def create_outbound_order(
    payload: StockExitCreate,
    current_user: dict = Depends(require_manager),
    session: Session = Depends(get_db),
) -> StockExitRead:
    exit_record = create_outbound(session, payload, str(current_user["id"]))
    return StockExitRead(
        id=exit_record.id,
        sku_id=exit_record.sku_id,
        quantity=exit_record.quantity,
        warehouse=exit_record.warehouse,
        user_uuid=exit_record.user_uuid,
        created_at=exit_record.created_at,
    )


@router.get(
    "/orders",
    response_model=list[InventoryOrderItem],
    summary="Listar todas las órdenes con datos del producto y user_uuid",
)
def list_orders(
    _=Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[InventoryOrderItem]:
    entries = session.exec(
        select(StockEntry).options(selectinload(StockEntry.product))
    ).all()
    exits = session.exec(
        select(StockExit).options(selectinload(StockExit.product))
    ).all()

    items = [
        InventoryOrderItem(
            id=entry.id,
            order_type="inbound",
            sku_id=entry.sku_id,
            product_name=entry.product.name if entry.product else "",
            warehouse=entry.warehouse,
            quantity=entry.quantity,
            user_uuid=entry.user_uuid,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
    items += [
        InventoryOrderItem(
            id=exit_record.id,
            order_type="outbound",
            sku_id=exit_record.sku_id,
            product_name=exit_record.product.name if exit_record.product else "",
            warehouse=exit_record.warehouse,
            quantity=exit_record.quantity,
            user_uuid=exit_record.user_uuid,
            created_at=exit_record.created_at,
        )
        for exit_record in exits
    ]
    items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    return items
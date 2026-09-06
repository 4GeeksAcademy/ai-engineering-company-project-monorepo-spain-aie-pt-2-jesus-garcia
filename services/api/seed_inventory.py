"""Seed determinista e idempotente de inventario (SKUs + entradas/salidas).

Ejecutarlo varias veces produce siempre el mismo estado: las tablas de
inventario se truncan y se repueblan con valores fijos.

Stock neto esperado por SKU (suma de ambos almacenes):
  CLT-SNK-W-42 -> 47   (los_angeles 47, zaragoza 0)
  CLT-SNK-B-42 -> 55   (los_angeles 40, zaragoza 15)
  RUN-SNK-R-41 -> 18   (los_angeles 0,  zaragoza 18)
  TRL-SNK-BL-43 -> 17  (los_angeles 0,  zaragoza 17)
"""

from datetime import datetime, timedelta, timezone
import sys

from sqlmodel import Session, SQLModel, delete, select

from database import engine
from app.services.inventory_service import compute_stock_by_warehouse
from models import SKU, StockEntry, StockExit

USER_UUID = "11111111-1111-1111-1111-111111111111"

BASE_DATE = datetime(2025, 6, 1, 10, 30, tzinfo=timezone.utc)

SKUS = [
    {
        "name": "Classic White Sneaker - Size 42",
        "sku_code": "CLT-SNK-W-42",
        "warehouse": "los_angeles",
    },
    {
        "name": "Classic Black Sneaker - Size 42",
        "sku_code": "CLT-SNK-B-42",
        "warehouse": "zaragoza",
    },
    {
        "name": "Runner Red Sneaker - Size 41",
        "sku_code": "RUN-SNK-R-41",
        "warehouse": "los_angeles",
    },
    {
        "name": "Trail Blue Sneaker - Size 43",
        "sku_code": "TRL-SNK-BL-43",
        "warehouse": "zaragoza",
    },
]

ENTRIES = [
    # (sku_code, quantity, warehouse)
    ("CLT-SNK-W-42", 50, "los_angeles"),
    ("CLT-SNK-B-42", 40, "los_angeles"),
    ("CLT-SNK-B-42", 20, "zaragoza"),
    ("RUN-SNK-R-41", 30, "zaragoza"),
    ("TRL-SNK-BL-43", 25, "zaragoza"),
]

EXITS = [
    # (sku_code, quantity, warehouse)
    ("CLT-SNK-W-42", 3, "los_angeles"),
    ("CLT-SNK-B-42", 5, "zaragoza"),
    ("RUN-SNK-R-41", 12, "zaragoza"),
    ("TRL-SNK-BL-43", 8, "zaragoza"),
]


def seed() -> list[dict]:
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL no está configurada. Definela en el entorno o en .env para usar la base de datos SQL."
        )

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))

        sku_id_by_code: dict[str, int] = {}
        for sku_data in SKUS:
            sku = SKU(**sku_data)
            session.add(sku)
            session.flush()
            sku_id_by_code[sku.sku_code] = sku.id

        for index, (sku_code, quantity, warehouse) in enumerate(ENTRIES):
            created_at = BASE_DATE + timedelta(minutes=index)
            session.add(
                StockEntry(
                    sku_id=sku_id_by_code[sku_code],
                    quantity=quantity,
                    warehouse=warehouse,
                    user_uuid=USER_UUID,
                    created_at=created_at,
                )
            )

        for index, (sku_code, quantity, warehouse) in enumerate(EXITS):
            created_at = (BASE_DATE + timedelta(minutes=len(ENTRIES) + index))
            session.add(
                StockExit(
                    sku_id=sku_id_by_code[sku_code],
                    quantity=quantity,
                    warehouse=warehouse,
                    user_uuid=USER_UUID,
                    created_at=created_at,
                )
            )

        session.commit()

        skus = session.exec(select(SKU).order_by(SKU.id)).all()
        summary = []
        for sku in skus:
            by_warehouse = compute_stock_by_warehouse(session, sku.id)
            summary.append(
                {
                    "sku_code": sku.sku_code,
                    "current_stock": sum(by_warehouse.values()),
                    "current_stock_by_warehouse": by_warehouse,
                }
            )
        return summary


def main():
    try:
        summary = seed()
    except Exception as exc:  # noqa: BLE001
        print(f"Error al seedear inventario: {exc}")
        sys.exit(1)
    print(f"Seed completado: {len(summary)} SKUs.")
    for row in summary:
        total = row["current_stock"]
        print(f"  {row['sku_code']}: {total} (by warehouse: {row['current_stock_by_warehouse']})")
    sys.exit(0)


if __name__ == "__main__":
    main()
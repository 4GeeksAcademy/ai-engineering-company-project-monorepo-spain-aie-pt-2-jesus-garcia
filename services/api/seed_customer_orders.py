"""Seed determinista de pedidos para el guard de autorización del agente.

No trunca ni borra: hace upsert por ``order_ref``. Los pedidos de demo cubren
los dos países y los dos propietarios que usan los tests/evidencia:

* ``1001`` — admin de TrackFlow, Estados Unidos.
* ``1002`` — admin de TrackFlow, España.
* ``45821`` — otro cliente, Estados Unidos (caso de acceso cruzado).
* ``45822`` — otro cliente, España (caso de acceso cruzado).

Uso::

    cd services/api && source venv/bin/activate
    python seed_customer_orders.py --dry-run
    python seed_customer_orders.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlmodel import Session, select

from database import engine
from models import CustomerOrder

ADMIN_EMAIL = "admin@trackflow.com"
OTHER_EMAIL = "cliente.otro@example.com"

ORDERS: tuple[dict, ...] = (
    {
        "order_ref": "1001",
        "owner_user_id": None,
        "owner_email": ADMIN_EMAIL,
        "country": "US",
        "carrier": "UPS",
        "status": "in_transit",
    },
    {
        "order_ref": "1002",
        "owner_user_id": None,
        "owner_email": ADMIN_EMAIL,
        "country": "ES",
        "carrier": "SEUR",
        "status": "delivered",
    },
    {
        "order_ref": "45821",
        "owner_user_id": None,
        "owner_email": OTHER_EMAIL,
        "country": "US",
        "carrier": "FedEx",
        "status": "delivered",
    },
    {
        "order_ref": "45822",
        "owner_user_id": None,
        "owner_email": OTHER_EMAIL,
        "country": "ES",
        "carrier": "MRW",
        "status": "in_transit",
    },
)


def seed_customer_orders(*, dry_run: bool = False) -> dict[str, int]:
    if engine is None:
        raise RuntimeError("DATABASE_URL no está configurada.")

    CustomerOrder.__table__.create(engine, checkfirst=True)
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        for data in ORDERS:
            existing = session.exec(
                select(CustomerOrder).where(
                    CustomerOrder.order_ref == data["order_ref"]
                )
            ).first()
            if existing is None:
                counts["created"] += 1
                if not dry_run:
                    session.add(CustomerOrder(**data, updated_at=now))
                continue

            changed = any(
                getattr(existing, field) != value
                for field, value in data.items()
                if field != "order_ref"
            )
            if changed:
                counts["updated"] += 1
                if not dry_run:
                    for field, value in data.items():
                        if field != "order_ref":
                            setattr(existing, field, value)
                    existing.updated_at = now
            else:
                counts["unchanged"] += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crea/actualiza pedidos de demo para el harness del agente."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el plan sin escribir en la base de datos.",
    )
    args = parser.parse_args()

    try:
        counts = seed_customer_orders(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - script de operación
        print(f"Error al sembrar pedidos: {exc}", file=sys.stderr)
        return 1

    print(
        "customer_order: "
        f"created={counts['created']} updated={counts['updated']} "
        f"unchanged={counts['unchanged']} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

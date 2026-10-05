"""Seed de carga realista para la auditoría de rendimiento.

Volúmenes objetivo moderados (escalables con --scale o flags individuales):
  - suppliers : 400      (TinyDB)
  - incidents : 5.000    (TinyDB)
  - users     : 200      (TinyDB) — para que el scan de auth y el join de user_email cuesten de verdad
  - skus      : 150      (PostgreSQL/SQLModel)
  - orders    : 20.000   (PostgreSQL/SQLModel)  — 40% inbound / 60% outbound

Determinista (Random(42)) e idempotente (trunca y repuebla cada tabla).
Inventario requiere DATABASE_URL configurada; si no, se omite con aviso.

Uso:
  python seed_perf.py                 # volúmenes objetivo
  python seed_perf.py --scale 5       # multiplica todos los volúmenes
  python seed_perf.py --incidents 10000 --orders 50000   # override individual
"""

from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta, timezone
import sys
from typing import Callable

from sqlalchemy import insert
from sqlmodel import SQLModel, Session, delete, select

from database import engine, get_tinydb
from app.core.security import hash_password
from models import (
    INCIDENT_BRANCHES,
    INCIDENT_CATEGORIES,
    INCIDENT_ORIGINS,
    INCIDENT_STATUSES,
    SKU,
    StockEntry,
    StockExit,
    VALID_CATEGORIES,
)

RNG = __import__("random").Random(42)

BASE_SUPPLIERS = 400
BASE_INCIDENTS = 5_000
BASE_USERS = 200
BASE_SKUS = 150
BASE_ORDERS = 20_000
BATCH = 2_000

CATEGORY_RATE = {
    "carrier_last_mile": (4.0, 16.0),
    "carrier_international": (10.0, 32.0),
    "warehouse_supplies": (0.5, 9.0),
    "packaging_materials": (0.1, 1.6),
    "reverse_logistics": (3.5, 9.5),
    "fleet_maintenance": (250.0, 2_000.0),
    "it_and_wms_software": (500.0, 4_000.0),
    "cleaning_and_facilities": (800.0, 4_000.0),
}

NAME_A = [
    "Global", "Iberia", "Atlantic", "Pacific", "Prime", "Swift", "Nova",
    "Metro", "Aero", "Blue", "Silver", "Apex", "Red", "North", "South",
    "Golden", "Clear", "Uni", "Twin", "Tri",
]
NAME_B = [
    "Logistics", "Solutions", "Express", "Carrier", "Freight", "Distribution",
    "Shipping", "Transit", "Couriers", "Transports", "Group", "Services",
    "Cargo", "Dispatch", "Ways",
]
ZONES_USA = [
    "West Coast", "East Coast", "Continental USA", "Southwest US",
    "Midwest USA", "Gulf Coast",
]
ZONES_ESP = [
    "Península Ibérica", "Aragón", "Madrid", "Cataluña", "Levante", "Norte",
]
EMAIL_DOMAINS = [
    "carriers.com", "logistics.io", "suppliers.es", "wms.cloud", "freight.net",
    "express.co", "transit.es",
]

CATEGORY_LABELS = {
    "lost_parcel": "Paquete perdido",
    "delivery_failure": "Fallo de entrega",
    "inventory_discrepancy": "Discrepancia de inventario",
    "carrier_issue": "Problema de carrier",
    "returns_issue": "Devolución",
    "warehouse_incident": "Incidente de almacén",
    "system_failure": "Fallo de sistema",
    "client_complaint": "Queja de cliente",
    "other": "Otro",
}
ROUTES_USA = [
    "LA - Downtown", "LA - Santa Mónica", "LA - Inglewood", "LA - Long Beach",
    "LA - Pasadena", "LA - Torrance", "LA - Glendale",
]
ROUTES_ESP = [
    "Zaragoza - Centro", "Zaragoza - Delicias", "Zaragoza - Actur",
    "Madrid - Chamartín", "Madrid - Atocha", "Barcelona - Poblenou",
]
DETAILS = [
    "El transportista no finalizó la entrega dentro de la ventana acordada.",
    "El cliente reporta no haber recibido el artículo pese a figurar como entregado.",
    "La discrepancia se detectó en el recuento físico del almacén.",
    "El sello del paquete estaba roto y el contenido parcialmente dañado.",
    "Se solicitó información de seguimiento y la ruta no actualiza desde hace 48 horas.",
    "El código postal indicado no coincide con la zona de reparto registrada.",
]

FIRST_NAMES = [
    "Carmen", "Luis", "Ana", "Jorge", "Lucía", "Diego", "Paula", "Rafael",
    "Marta", "Pablo", "Sofía", "Andrés", "Clara", "Miguel", "Elena", "Óscar",
]
LAST_NAMES = [
    "García", "Martínez", "López", "Sánchez", "Rodríguez", "Fernández",
    "Pérez", "Gómez", "Ruiz", "Díaz", "Moreno", "Álvarez", "Romero",
    "Navarro", "Torres", "Domínguez",
]

SKU_FAMILIES = [
    ("CLT-SNK", "Classic Sneaker"),
    ("RUN-SNK", "Runner Sneaker"),
    ("TRL-BT", "Trail Boot"),
    ("CT-ORK", "Comfort Boot"),
    ("SN-CAN", "Canvas Sneaker"),
    ("SL-SLD", "Slip-on"),
    ("SP-ATL", "Athletic Shoe"),
    ("TR-CR", "Track Runner"),
]
COLORS = ["White", "Black", "Red", "Blue", "Green", "Grey", "Tan", "Beige"]
COLOR_CODES = ["W", "B", "R", "BL", "G", "GR", "T", "BE"]
SIZES = list(range(36, 46))


def weighted(pairs: list[tuple[str, int]]) -> str:
    total = sum(weight for _, weight in pairs)
    roll = RNG.uniform(0, total)
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if roll <= acc:
            return value
    return pairs[-1][0]


def _created_at(span_days: int = 540) -> datetime:
    start = datetime.now(timezone.utc) - timedelta(days=span_days)
    return start + timedelta(seconds=RNG.randint(0, span_days * 86_400))


def seed_users(count: int) -> list[str]:
    db = get_tinydb()
    users = db.table("users")
    profiles = db.table("profiles")
    users.truncate()
    profiles.truncate()

    now = datetime.now(timezone.utc).isoformat()
    user_rows = []
    profile_rows = []
    uuids: list[str] = []

    for i in range(count):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        name = f"{first} {last}"
        domain = RNG.choice(EMAIL_DOMAINS)
        email = f"{first.lower()}.{last.lower()}{i}@{domain}"
        role = "admin" if i == 0 else weighted([("user", 86), ("manager", 10), ("admin", 4)])
        password = "admin123" if i == 0 else "perf-password"
        user_rows.append({
            "email": email,
            "hashed_password": hash_password(password),
            "is_active": True,
            "role": role,
            "created_at": now,
        })

    users.insert_multiple(user_rows)
    for doc in users.all():
        uuids.append(str(doc.doc_id))
        first = FIRST_NAMES[int(doc.doc_id) % len(FIRST_NAMES)]
        last = LAST_NAMES[int(doc.doc_id) % len(LAST_NAMES)]
        profile_rows.append({
            "user_id": str(doc.doc_id),
            "name": f"{first} {last}",
            "phone": f"+34 6{RNG.randint(10, 99)} {RNG.randint(100, 999)} {RNG.randint(100, 999)}",
            "address": f"Calle {RNG.choice(['Mayor', 'Sol', 'Alonso', 'Zurita', 'Pilar'])} {RNG.randint(1, 200)}",
        })
    profiles.insert_multiple(profile_rows)
    db.close()
    return uuids


def seed_suppliers(count: int) -> None:
    db = get_tinydb()
    table = db.table("suppliers")
    table.truncate()

    rows = []
    for i in range(count):
        country = "Spain" if (i % 2) == 0 else "USA"
        categories = []
        primary = VALID_CATEGORIES[i % len(VALID_CATEGORIES)]
        categories.append(primary)
        if RNG.random() < 0.3:
            secondary = RNG.choice([c for c in VALID_CATEGORIES if c != primary])
            categories.append(secondary)
        low, high = CATEGORY_RATE[primary]
        zone = RNG.choice(ZONES_ESP) if country == "Spain" else RNG.choice(ZONES_USA)
        name = f"{RNG.choice(NAME_A)} {RNG.choice(NAME_B)}"
        safe = name.lower().replace(" ", ".")
        email = f"{safe}{RNG.randint(10, 999)}@{RNG.choice(EMAIL_DOMAINS)}"
        rows.append({
            "name": name,
            "country": country,
            "categories": categories,
            "rate_per_shipment": round(RNG.uniform(low, high), 2),
            "currency": "EUR" if country == "Spain" else "USD",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "suspended" if RNG.random() < 0.08 else "active",
            "service_zone": zone,
            "contact_email": email,
            "notes": "Proveedor cargado por seed_perf para auditoría de rendimiento." if RNG.random() < 0.2 else None,
        })
    table.insert_multiple(rows)
    db.close()


def seed_incidents(count: int) -> None:
    db = get_tinydb()
    table = db.table("incidents")
    table.truncate()

    rows = []
    route_pool = ROUTES_USA + ROUTES_ESP
    origin_weights = [("customer", 72), ("branch", 18), ("internal", 10)]
    status_weights = [("open", 20), ("in_progress", 15), ("resolved", 50), ("discarded", 15)]

    for i in range(count):
        created = _created_at()
        status = weighted(status_weights)
        updated = created
        if status in ("resolved", "discarded"):
            updated = min(created + timedelta(days=RNG.randint(1, 12)),
                          datetime.now(timezone.utc))
        elif status == "in_progress":
            updated = created + timedelta(days=RNG.randint(1, 3))
        origin = weighted(origin_weights)
        category = weighted([
            ("lost_parcel", 15), ("delivery_failure", 22), ("inventory_discrepancy", 12),
            ("carrier_issue", 18), ("returns_issue", 14), ("warehouse_incident", 7),
            ("system_failure", 5), ("client_complaint", 5), ("other", 2),
        ])
        branch = INCIDENT_BRANCHES[i % len(INCIDENT_BRANCHES)]
        route = route_pool[(i * 7) % len(route_pool)]
        label = CATEGORY_LABELS[category]
        rows.append({
            "title": f"{label} en {route} (caso {i + 1})",
            "description": f"Nº {i + 1} — {RNG.choice(DETAILS)}",
            "origin": origin,
            "branch": branch,
            "category": category,
            "status": status,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        })
    table.insert_multiple(rows)
    db.close()


def _build_sku_rows(n_skus: int) -> list[dict]:
    rows = []
    used_codes: set[str] = set()
    attempts = 0
    while len(rows) < n_skus and attempts < n_skus * 50:
        attempts += 1
        family, label = SKU_FAMILIES[len(rows) % len(SKU_FAMILIES)]
        color, color_code = RNG.choice(list(zip(COLORS, COLOR_CODES)))
        size = RNG.choice(SIZES)
        code = f"{family}-{color_code}-{size}"
        if code in used_codes:
            continue
        used_codes.add(code)
        rows.append({
            "name": f"{label} {color} - Size {size}",
            "sku_code": code,
            "warehouse": "los_angeles" if len(rows) % 2 == 0 else "zaragoza",
        })
    if len(rows) < n_skus:
        for i in range(len(rows), n_skus):
            code = f"PERF-FAM-{i}"
            used_codes.add(code)
            rows.append({
                "name": f"Perf Product {i}",
                "sku_code": code,
                "warehouse": "los_angeles" if i % 2 == 0 else "zaragoza",
            })
    return rows


def seed_inventory(n_skus: int, n_orders: int, user_uuids: list[str]) -> None:
    if engine is None:
        print("  [skip] Inventario: DATABASE_URL no configurada (engine None).")
        return
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()

        sku_rows = _build_sku_rows(n_skus)
        session.execute(insert(SKU), sku_rows)
        session.commit()

        code_to_id: dict[str, int] = {
            sku.sku_code: sku.id for sku in session.exec(select(SKU)).all()
        }

        entries: list[dict] = []
        exits: list[dict] = []
        for i in range(n_orders):
            sku_id = code_to_id[sku_rows[i % len(sku_rows)]["sku_code"]]
            sku = sku_rows[i % len(sku_rows)]
            warehouse = sku["warehouse"] if RNG.random() < 0.6 else RNG.choice(
                ["los_angeles", "zaragoza"]
            )
            created = _created_at(span_days=365)
            uuid = user_uuids[i % len(user_uuids)]
            if i % 5 < 2:
                entries.append({
                    "sku_id": sku_id,
                    "quantity": RNG.randint(10, 120),
                    "warehouse": warehouse,
                    "user_uuid": uuid,
                    "created_at": created,
                })
            else:
                exits.append({
                    "sku_id": sku_id,
                    "quantity": RNG.randint(1, 40),
                    "warehouse": warehouse,
                    "user_uuid": uuid,
                    "created_at": created,
                })

        for table_model, rows in ((StockEntry, entries), (StockExit, exits)):
            for start in range(0, len(rows), BATCH):
                session.execute(insert(table_model), rows[start:start + BATCH])
                session.commit()

    print(f"  Inventario: {len(sku_rows)} SKUs, {len(entries)} entradas, {len(exits)} salidas.")


def parse_args(argv: list[str]) -> Namespace:
    parser = ArgumentParser(description="Carga realista para auditoría de rendimiento")
    parser.add_argument("--scale", type=int, default=1, help="Multiplica los volúmenes objetivo (default 1).")
    parser.add_argument("--suppliers", type=int, default=None)
    parser.add_argument("--incidents", type=int, default=None)
    parser.add_argument("--users", type=int, default=None)
    parser.add_argument("--skus", type=int, default=None)
    parser.add_argument("--orders", type=int, default=None)
    return parser.parse_args(argv)


def resolve_count(flag: int | None, base: int, scale: int) -> int:
    return flag if flag is not None else base * scale


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    scale = max(1, args.scale)
    suppliers = resolve_count(args.suppliers, BASE_SUPPLIERS, scale)
    incidents = resolve_count(args.incidents, BASE_INCIDENTS, scale)
    users = resolve_count(args.users, BASE_USERS, scale)
    skus = resolve_count(args.skus, BASE_SKUS, scale)
    orders = resolve_count(args.orders, BASE_ORDERS, scale)

    print("Plan de carga:")
    print(f"  suppliers: {suppliers} | incidents: {incidents} | users: {users} | skus: {skus} | orders: {orders}")
    print("Truncando y repoblando tablas…")

    uuids = seed_users(users)
    print(f"  Usuarios + perfiles: {len(uuids)} insertados. admin@trackflow.com / admin123 (role admin).")
    seed_suppliers(suppliers)
    print(f"  Suppliers: {suppliers} insertados.")
    seed_incidents(incidents)
    print(f"  Incidents: {incidents} insertados.")
    seed_inventory(skus, orders, uuids)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error al seedear: {exc}")
        sys.exit(1)
#!/usr/bin/env python3
"""Siembra demo del SLA de entrega por país (read model de reporting).

El pipeline semanal de desempeño no mide entregas; este script rellena
``reporting.delivery_sla_weekly`` con una semana reproducible para poder ver la
alerta de umbral del briefing (``sla_threshold_alert``) de punta a punta:

* ``US`` / ``los_angeles`` — 88,4 % (por debajo del 90 % → dispara la alerta).
* ``Spain`` / ``zaragoza`` — 93,1 % (por encima → no dispara).

Uso::

    python scripts/seed_delivery_sla.py
    python scripts/seed_delivery_sla.py --week 2026-11-09 --force
    python scripts/seed_delivery_sla.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(API_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import text  # noqa: E402
from sqlmodel import Session  # noqa: E402

from database import engine  # noqa: E402
from services.reporting.sla import (  # noqa: E402
    SLA_THRESHOLD_PCT,
    ensure_sla_table,
)

# (country, warehouse, total_shipments, on_time_shipments)
DEMO_ROWS: tuple[tuple[str, str, int, int], ...] = (
    ("US", "los_angeles", 1520, 1344),  # 88.4 % -> por debajo del umbral
    ("Spain", "zaragoza", 980, 912),  # 93.1 % -> ok
)


def last_monday(today: date | None = None) -> date:
    current = today or date.today()
    return current - timedelta(days=current.weekday())


def seed(week_start: date, *, force: bool, dry_run: bool) -> int:
    if engine is None:
        print("DATABASE_URL no está configurada.", file=sys.stderr)
        return 2

    ensure_sla_table(engine)
    table = _qualified_for_engine()

    with Session(engine) as session:
        existing = session.execute(
            text(f"select count(*) from {table} where week_start = :week"),
            {"week": week_start},
        ).scalar()
        if existing and not force:
            print(
                f"La semana {week_start} ya tiene datos. Usa --force para reemplazar."
            )
            return 1

        rows = DEMO_ROWS
        if dry_run:
            for country, warehouse, total, on_time in rows:
                pct = round(on_time / total * 100, 1)
                flag = "ALERTA" if pct < SLA_THRESHOLD_PCT else "ok"
                print(f"{week_start} {country}: {pct}% [{flag}]")
            return 0

        if force:
            session.execute(
                text(f"delete from {table} where week_start = :week"),
                {"week": week_start},
            )

        now = datetime.now(timezone.utc)
        for country, warehouse, total, on_time in rows:
            session.execute(
                text(
                    f"""
                    insert into {table}
                        (id, week_start, country, warehouse, total_shipments,
                         on_time_shipments, computed_at)
                    values
                        (:id, :week, :country, :warehouse, :total, :on_time,
                         :computed_at)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "week": week_start,
                    "country": country,
                    "warehouse": warehouse,
                    "total": total,
                    "on_time": on_time,
                    "computed_at": now,
                },
            )
        session.commit()

    print(f"Sembrada la semana {week_start} en {table}.")
    for country, warehouse, total, on_time in rows:
        pct = round(on_time / total * 100, 1)
        flag = "ALERTA" if pct < SLA_THRESHOLD_PCT else "ok"
        print(f"  {country} ({warehouse}): {pct}% [{flag}]")
    return 0


def _qualified_for_engine() -> str:
    if engine is None:
        return "delivery_sla_weekly"
    prefix = "reporting." if engine.dialect.name == "postgresql" else ""
    return f"{prefix}delivery_sla_weekly"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week",
        help="Lunes ISO de la semana (por defecto, el lunes de esta semana).",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    week = date.fromisoformat(args.week) if args.week else last_monday()
    if week.weekday() != 0:
        print("La semana debe ser lunes (week_start ISO).", file=sys.stderr)
        return 2
    return seed(week, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

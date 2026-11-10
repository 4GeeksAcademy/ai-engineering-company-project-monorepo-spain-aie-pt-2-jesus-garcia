"""Importa el mapeo SKU → client_id / min_stock desde un CSV.

Formato:
    sku_code,client_id,min_stock
    CLT-SNK-W-42,fashion-co,10
    RUN-SNK-R-41,home-deco,

- `client_id` vacío ⇒ NULL (pendiente de mapeo).
- `min_stock` vacío ⇒ NULL (umbral no configurado).
- No borra ni crea SKUs: solo actualiza los existentes.
- Contra una BD remota exige `--allow-remote-db`.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

from sqlmodel import Session, select

from database import DATABASE_URL, engine
from models import SKU
from seed_guard import is_remote_database_url, mask_database_url

REQUIRED_HEADERS = {"sku_code", "client_id", "min_stock"}


def parse_csv(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_HEADERS - headers
        if missing:
            return [], [f"Faltan columnas: {', '.join(sorted(missing))}"]

        for line_number, raw in enumerate(reader, start=2):
            sku_code = (raw.get("sku_code") or "").strip()
            if not sku_code:
                errors.append(f"Línea {line_number}: sku_code vacío")
                continue

            client_id = (raw.get("client_id") or "").strip() or None
            min_stock_raw = (raw.get("min_stock") or "").strip()
            if min_stock_raw:
                try:
                    min_stock = int(min_stock_raw)
                except ValueError:
                    errors.append(
                        f"Línea {line_number}: min_stock no es entero ({min_stock_raw!r})"
                    )
                    continue
                if min_stock < 0:
                    errors.append(
                        f"Línea {line_number}: min_stock no puede ser negativo"
                    )
                    continue
            else:
                min_stock = None

            rows.append(
                {
                    "sku_code": sku_code,
                    "client_id": client_id,
                    "min_stock": min_stock,
                }
            )

    return rows, errors


def apply_mapping(
    session: Session,
    rows: list[dict],
    *,
    dry_run: bool = False,
) -> dict:
    updated = 0
    unchanged = 0
    not_found: list[str] = []

    for row in rows:
        sku = session.exec(
            select(SKU).where(SKU.sku_code == row["sku_code"])
        ).first()
        if sku is None:
            not_found.append(row["sku_code"])
            continue

        if sku.client_id == row["client_id"] and sku.min_stock == row["min_stock"]:
            unchanged += 1
            continue

        if not dry_run:
            sku.client_id = row["client_id"]
            sku.min_stock = row["min_stock"]
            session.add(sku)
        updated += 1

    if not dry_run:
        session.commit()

    return {
        "updated": updated,
        "unchanged": unchanged,
        "not_found": not_found,
        "dry_run": dry_run,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importa el mapeo SKU → cliente / min_stock desde CSV."
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-remote-db", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if engine is None:
        print("DATABASE_URL no configurada.", file=sys.stderr)
        return 2

    if is_remote_database_url(DATABASE_URL) and not args.allow_remote_db:
        print(
            f"[ABORTADO] DATABASE_URL es remota: {mask_database_url(DATABASE_URL)}\n"
            "Reejecuta con --allow-remote-db si es intencional.",
            file=sys.stderr,
        )
        return 2

    rows, errors = parse_csv(args.file)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}", file=sys.stderr)
        print("No se ha modificado nada.", file=sys.stderr)
        return 1

    with Session(engine) as session:
        summary = apply_mapping(session, rows, dry_run=args.dry_run)

    print(f"BD: {mask_database_url(DATABASE_URL)}")
    print(
        f"Actualizados: {summary['updated']} | "
        f"Sin cambios: {summary['unchanged']} | "
        f"No encontrados: {len(summary['not_found'])}"
    )
    if summary["not_found"]:
        print("SKUs no encontrados: " + ", ".join(summary["not_found"]))
    if summary["dry_run"]:
        print("[dry-run] No se ha modificado nada.")

    return 1 if summary["not_found"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

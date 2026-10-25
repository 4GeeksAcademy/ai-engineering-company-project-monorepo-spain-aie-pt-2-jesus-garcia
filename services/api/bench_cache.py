"""Benchmark reproducible de la caché (cold vs warm) — CACHING_REPORT.md.

Mide con `TestClient` + `time.perf_counter` el coste de cada endpoint cacheado:
  - cold = `cache.clear()` y una petición (incluye el scan de auth, ≈ coste sin caché).
  - warm = petición inmediata siguiente con la caché caliente.
Se ejecutan `--repeats` cadencias (por defecto 3) y se reporta el **mínimo** de
cada serie para reducir el ruido del scheduler.

Requisitos:
  1. Datos de carga (destructivo):
       python seed_perf.py --force
  2. Para inventario, sembrar y medir contra una base local (no Supabase):
       DATABASE_URL=sqlite:///./perf_measure.db python seed_perf.py --force
       DATABASE_URL=sqlite:///./perf_measure.db python bench_cache.py
     Sin `DATABASE_URL`, los endpoints `/inventory/*` se omiten con aviso.

Uso:
  python bench_cache.py                 # 3 cadencias, tabla markdown
  python bench_cache.py --repeats 5
  python bench_cache.py --json          # salida JSON
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.cache import cache  # noqa: E402
from app.core.security import create_token  # noqa: E402
from app.main import create_app  # noqa: E402
from database import engine, get_tinydb  # noqa: E402

# Endpoints medidos (etiqueta, path). El token usa el admin sembrado (doc_id 1).
ENDPOINTS: list[tuple[str, str]] = [
    ("GET /api/suppliers", "/api/suppliers"),
    ("GET /api/suppliers?country=USA", "/api/suppliers?country=USA"),
    ("GET /api/incidents", "/api/incidents"),
    ("GET /api/incidents?status=open", "/api/incidents?status=open"),
    ("GET /api/incidents/summary", "/api/incidents/summary"),
    ("GET /api/incidents/1", "/api/incidents/1"),
    ("GET /api/auth/me", "/api/auth/me"),
]

INVENTORY_ENDPOINTS: list[tuple[str, str]] = [
    ("GET /inventory/products", "/inventory/products"),
    ("GET /inventory/products/1", "/inventory/products/1"),
    ("GET /inventory/orders", "/inventory/orders"),
]


def _volumes() -> dict[str, int]:
    db = get_tinydb()
    volumes = {
        "suppliers": len(db.table("suppliers").all()),
        "incidents": len(db.table("incidents").all()),
        "users": len(db.table("users").all()),
    }
    db.close()
    if engine is not None:
        from sqlmodel import Session, select

        from models import SKU, StockEntry, StockExit

        with Session(engine) as session:
            volumes["skus"] = len(session.exec(select(SKU)).all())
            volumes["stock_entries"] = len(session.exec(select(StockEntry)).all())
            volumes["stock_exits"] = len(session.exec(select(StockExit)).all())
    return volumes


def _measure(client: TestClient, path: str, headers: dict, repeats: int):
    """Devuelve ((cold_ms, warm_ms), status) con el mínimo de `repeats` cadencias."""
    colds: list[float] = []
    warms: list[float] = []
    status = 0
    for _ in range(repeats):
        cache.clear()
        start = time.perf_counter()
        response = client.get(path, headers=headers)
        colds.append((time.perf_counter() - start) * 1000)
        status = response.status_code
        if status != 200:
            return None, status

        start = time.perf_counter()
        client.get(path, headers=headers)
        warms.append((time.perf_counter() - start) * 1000)
    return (min(colds), min(warms)), status


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark cold/warm de la caché.")
    parser.add_argument("--repeats", type=int, default=3, help="Cadencias (default 3).")
    parser.add_argument("--json", action="store_true", help="Salida en JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repeats = max(1, args.repeats)

    logging.getLogger("api.timing").setLevel(logging.WARNING)

    volumes = _volumes()
    if volumes.get("suppliers", 0) == 0 or volumes.get("users", 0) == 0:
        print(
            "No hay datos sembrados. Ejecuta primero:  python seed_perf.py --force",
            file=sys.stderr,
        )
        return 1

    app = create_app()
    headers = {"Authorization": f"Bearer {create_token({'sub': '1', 'role': 'admin'})}"}

    endpoints = list(ENDPOINTS)
    if engine is not None:
        endpoints += INVENTORY_ENDPOINTS

    results = []
    skipped = []
    with TestClient(app) as client:
        for label, path in endpoints:
            measured, status = _measure(client, path, headers, repeats)
            if measured is None:
                skipped.append((label, status))
                continue
            cold, warm = measured
            delta = (warm - cold) / cold * 100 if cold else 0.0
            results.append(
                {"endpoint": label, "cold_ms": cold, "warm_ms": warm, "delta_pct": delta}
            )

    if args.json:
        print(json.dumps({"volumes": volumes, "results": results, "skipped": skipped}, indent=2))
        return 0

    print(f"Volúmenes: {volumes}")
    print(f"Cadencias (repeats): {repeats} · métrica: mínimo de la serie · TTL según CACHING_REPORT.md\n")
    print("| Endpoint | Cold (≈ antes) | Warm (después) | Δ |")
    print("|---|---:|---:|---:|")
    for row in results:
        print(
            f"| `{row['endpoint']}` | {row['cold_ms']:.1f} | {row['warm_ms']:.1f} "
            f"| {row['delta_pct']:+.0f} % |"
        )
    for label, status in skipped:
        print(f"\n[skip] {label} → HTTP {status} (¿datos/DB no sembrados?)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

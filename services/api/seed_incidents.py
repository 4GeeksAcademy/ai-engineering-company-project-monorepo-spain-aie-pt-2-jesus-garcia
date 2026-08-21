"""Deterministic seed para el Gestor de Incidencias Centralizado.

Genera los 95 registros esperados en docs/CONTEXT_centralized_incident_manager.md.
Idempotente: trunca la tabla de incidencias y la repuebla.

Salida esperada de /api/incidents/summary (post-transformación):
  por status:   open 29, resolved 52, discarded 14
  por category: lost_parcel 14, carrier_issue 45, delivery_failure 19, returns_issue 17
"""

from datetime import datetime, timedelta, timezone

from database import get_db

# Reparto por categoría -> (open, resolved, discarded); suma 95 en total.
SPLIT = {
    "lost_parcel": (5, 8, 1),
    "carrier_issue": (14, 26, 5),
    "delivery_failure": (6, 11, 2),
    "returns_issue": (4, 7, 6),
}

BRANCHES = ["la_office", "zaragoza_office"]

ORIGIN = "customer"


def iter_status_counts():
    for category, (open_n, resolved_n, discarded_n) in SPLIT.items():
        for status, count in (("open", open_n), ("resolved", resolved_n), ("discarded", discarded_n)):
            yield category, status, count


def build_records() -> list[dict]:
    base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    records = []
    index = 0
    for category, status, count in iter_status_counts():
        for i in range(count):
            index += 1
            created_at = (base_date + timedelta(days=index)).isoformat()
            branch = BRANCHES[index % len(BRANCHES)]
            title = f"Incidencia {index}: {category.replace('_', ' ')} ({status})"
            records.append(
                {
                    "title": title,
                    "description": f"Registro de ejemplo {index} de categoría {category} reportado por un cliente.",
                    "origin": ORIGIN,
                    "branch": branch,
                    "category": category,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )
    return records


def seed() -> int:
    db = get_db()
    table = db.table("incidents")
    table.truncate()
    records = build_records()
    table.insert_multiple(records)
    db.close()
    return len(records)


if __name__ == "__main__":
    total = seed()
    print(f"Seed completado: {total} incidencias insertadas.")

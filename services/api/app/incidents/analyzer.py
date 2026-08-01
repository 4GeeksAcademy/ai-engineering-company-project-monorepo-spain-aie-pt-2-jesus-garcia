"""Lógica compartida de validación y análisis de incidentes.

Este módulo es agnóstico a FastAPI y se reutiliza tanto desde la API
(services/api) como desde el script CLI (analyze.py en la raíz).
"""

import re
from typing import IO

import pandas as pd

CHUNK_SIZE = 10_000

REQUIRED_COLUMNS = [
    "customer_id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "department",
    "status",
    "category",
]

ALLOWED_DEPARTMENTS = {"Experiencia del cliente"}
ALLOWED_STATUSES = {"abierto", "cerrado", "descartado"}
ALLOWED_CATEGORIES = {"seguimiento", "devolución", "consulta_general", "incidencia"}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_record(row: dict) -> tuple[bool, list[str]]:
    """Validate a single record and return (is_valid, list_of_errors)."""
    errors: list[str] = []

    for col in REQUIRED_COLUMNS:
        value = row.get(col)
        if value is None or str(value).strip() == "":
            errors.append(f"missing_{col}")

    if not errors:
        email = str(row.get("email", "")).strip()
        if not EMAIL_RE.match(email):
            errors.append("invalid_email")

    department = str(row.get("department", "")).strip()
    if department and department not in ALLOWED_DEPARTMENTS:
        errors.append("invalid_department")

    status = str(row.get("status", "")).strip()
    if status and status not in ALLOWED_STATUSES:
        errors.append("invalid_status")

    category = str(row.get("category", "")).strip()
    if category and category not in ALLOWED_CATEGORIES:
        errors.append("invalid_category")

    satisfaction = str(row.get("satisfaction_score", "")).strip()
    if satisfaction:
        try:
            score = float(satisfaction)
            if score < 0 or score > 10:
                errors.append("invalid_satisfaction_score")
        except ValueError:
            errors.append("invalid_satisfaction_score")

    return len(errors) == 0, errors


def analyze_file(
    source: str | IO,
    chunk_size: int = CHUNK_SIZE,
    collect_invalid: bool = False,
) -> dict:
    """Read a CSV (path or file-like object) in chunks and compute summary stats.

    When ``collect_invalid`` is True, the result also includes ``invalid_rows``
    with the original fields plus an ``errors`` column (used by the CLI script).
    """
    stats = {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "by_status": {status: 0 for status in ALLOWED_STATUSES},
        "satisfaction_scores": [],
        "invalid_reasons": {},
        "invalid_rows": [],
    }

    reader = pd.read_csv(
        source,
        chunksize=chunk_size,
        dtype=str,
        keep_default_na=False,
    )

    for chunk in reader:
        for _, row in chunk.iterrows():
            stats["total"] += 1
            record = row.to_dict()
            is_valid, errors = validate_record(record)

            if not is_valid:
                stats["invalid"] += 1
                for error in errors:
                    stats["invalid_reasons"][error] = stats["invalid_reasons"].get(error, 0) + 1
                if collect_invalid:
                    stats["invalid_rows"].append({**record, "errors": ";".join(errors)})
                continue

            stats["valid"] += 1
            status = str(record.get("status", "")).strip()
            stats["by_status"][status] += 1

            satisfaction = str(record.get("satisfaction_score", "")).strip()
            if status == "cerrado" and satisfaction:
                stats["satisfaction_scores"].append(float(satisfaction))

    scores = stats.pop("satisfaction_scores")
    stats["avg_satisfaction_cerrados"] = round(sum(scores) / len(scores), 2) if scores else None
    return stats


def metrics_to_csv_rows(stats: dict) -> list[dict]:
    """Convert summary stats into metric/value rows for CSV export."""
    avg = stats.get("avg_satisfaction_cerrados")
    rows = [
        {"metrica": "total_registros", "valor": stats["total"]},
        {"metrica": "registros_validos", "valor": stats["valid"]},
        {"metrica": "registros_invalidos", "valor": stats["invalid"]},
        {"metrica": "estado_abierto", "valor": stats["by_status"]["abierto"]},
        {"metrica": "estado_cerrado", "valor": stats["by_status"]["cerrado"]},
        {"metrica": "estado_descartado", "valor": stats["by_status"]["descartado"]},
        {"metrica": "satisfaccion_media_cerrados", "valor": avg if avg is not None else ""},
    ]
    for reason, count in sorted(stats["invalid_reasons"].items()):
        rows.append({"metrica": f"invalido_{reason}", "valor": count})
    return rows

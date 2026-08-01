import csv
import re
import sys
from pathlib import Path

import pandas as pd

CSV_FILE = Path(__file__).parent / "COMPANY.csv"
RESULTS_FILE = Path(__file__).parent / "results.csv"
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


def process_csv(file_path: Path) -> dict:
    """Process CSV in chunks and compute summary statistics."""
    stats = {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "by_status": {status: 0 for status in ALLOWED_STATUSES},
        "satisfaction_scores": [],
        "invalid_reasons": {},
        "invalid_rows": [],
    }

    for chunk in pd.read_csv(
        file_path,
        chunksize=CHUNK_SIZE,
        dtype=str,
        keep_default_na=False,
    ):
        for _, row in chunk.iterrows():
            stats["total"] += 1
            record = row.to_dict()
            is_valid, errors = validate_record(record)

            if not is_valid:
                stats["invalid"] += 1
                for error in errors:
                    stats["invalid_reasons"][error] = stats["invalid_reasons"].get(error, 0) + 1
                stats["invalid_rows"].append({**record, "errors": ";".join(errors)})
                continue

            stats["valid"] += 1
            status = str(record.get("status", "")).strip()
            stats["by_status"][status] += 1

            satisfaction = str(record.get("satisfaction_score", "")).strip()
            if status == "cerrado" and satisfaction:
                stats["satisfaction_scores"].append(float(satisfaction))

    return stats


def print_summary(stats: dict) -> None:
    """Print a readable summary to the console."""
    total = stats["total"]
    valid = stats["valid"]
    invalid = stats["invalid"]
    avg_satisfaction = (
        sum(stats["satisfaction_scores"]) / len(stats["satisfaction_scores"])
        if stats["satisfaction_scores"]
        else 0.0
    )

    line_width = 50

    print("=" * line_width)
    print("  ANÁLISIS DE CASOS - Experiencia del cliente")
    print("=" * line_width)
    print(f"{'Total de registros procesados':<40} {total:>8}")
    print(f"{'Registros válidos':<40} {valid:>8}")
    print(f"{'Registros inválidos':<40} {invalid:>8}")
    print("-" * line_width)
    print("Total por estado:")
    for status in ALLOWED_STATUSES:
        label = status.capitalize()
        print(f"  {label:<37} {stats['by_status'][status]:>8}")
    print("-" * line_width)
    print(f"{'Índice de satisfacción medio (cerrados)':<40} {avg_satisfaction:>8.2f}")
    print("=" * line_width)

    if stats["invalid_reasons"]:
        print("\nDetalle de registros inválidos:")
        print("-" * line_width)
        for reason, count in sorted(stats["invalid_reasons"].items()):
            print(f"  {reason:<37} {count:>8}")
        print("=" * line_width)


def export_results(stats: dict) -> None:
    """Export summary metrics and invalid rows to a CSV file."""
    total = stats["total"]
    valid = stats["valid"]
    invalid = stats["invalid"]
    avg_satisfaction = (
        sum(stats["satisfaction_scores"]) / len(stats["satisfaction_scores"])
        if stats["satisfaction_scores"]
        else 0.0
    )

    summary_rows = [
        {"metrica": "total_registros", "valor": total},
        {"metrica": "registros_validos", "valor": valid},
        {"metrica": "registros_invalidos", "valor": invalid},
        {"metrica": "estado_abierto", "valor": stats["by_status"]["abierto"]},
        {"metrica": "estado_cerrado", "valor": stats["by_status"]["cerrado"]},
        {"metrica": "estado_descartado", "valor": stats["by_status"]["descartado"]},
        {"metrica": "satisfaccion_media_cerrados", "valor": round(avg_satisfaction, 2)},
    ]

    for reason, count in sorted(stats["invalid_reasons"].items()):
        summary_rows.append({"metrica": f"invalido_{reason}", "valor": count})

    with RESULTS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metrica", "valor"])
        writer.writeheader()
        writer.writerows(summary_rows)

    if stats["invalid_rows"]:
        invalid_file = RESULTS_FILE.with_name("results_invalid.csv")
        with invalid_file.open("w", newline="", encoding="utf-8") as f:
            fieldnames = list(stats["invalid_rows"][0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(stats["invalid_rows"])
        print(f"\nRegistros inválidos exportados a: {invalid_file.name}")

    print(f"\nResultados exportados a: {RESULTS_FILE.name}")


def ask_export() -> bool:
    """Ask the user whether to export the results."""
    while True:
        answer = input("\n¿Desea exportar los resultados a CSV? [s / n] ").strip().lower()
        if answer in {"s", "si", "sí", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Respuesta no reconocida. Escriba 's' para sí o 'n' para no.")


def main() -> int:
    if not CSV_FILE.exists():
        print(f"Error: no se encontró el archivo {CSV_FILE}")
        return 1

    stats = process_csv(CSV_FILE)
    print_summary(stats)

    if ask_export():
        export_results(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())

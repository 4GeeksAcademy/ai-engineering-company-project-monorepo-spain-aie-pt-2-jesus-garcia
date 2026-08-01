import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "services"))

from api.app.incidents.analyzer import (  # noqa: E402
    ALLOWED_STATUSES,
    analyze_file,
    metrics_to_csv_rows,
)

CSV_FILE = Path(__file__).parent / "COMPANY.csv"
RESULTS_FILE = Path(__file__).parent / "results.csv"


def print_summary(stats: dict) -> None:
    """Print a readable summary to the console."""
    line_width = 50

    print("=" * line_width)
    print("  ANÁLISIS DE CASOS - Experiencia del cliente")
    print("=" * line_width)
    print(f"{'Total de registros procesados':<40} {stats['total']:>8}")
    print(f"{'Registros válidos':<40} {stats['valid']:>8}")
    print(f"{'Registros inválidos':<40} {stats['invalid']:>8}")
    print("-" * line_width)
    print("Total por estado:")
    for status in ALLOWED_STATUSES:
        label = status.capitalize()
        print(f"  {label:<37} {stats['by_status'][status]:>8}")
    print("-" * line_width)
    avg = stats["avg_satisfaction_cerrados"]
    print(f"{'Índice de satisfacción medio (cerrados)':<40} {avg if avg is not None else 'n/d':>8}")
    print("=" * line_width)

    if stats["invalid_reasons"]:
        print("\nDetalle de registros inválidos:")
        print("-" * line_width)
        for reason, count in sorted(stats["invalid_reasons"].items()):
            print(f"  {reason:<37} {count:>8}")
        print("=" * line_width)


def export_results(stats: dict) -> None:
    """Export summary metrics and invalid rows to CSV files."""
    with RESULTS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metrica", "valor"])
        writer.writeheader()
        writer.writerows(metrics_to_csv_rows(stats))

    if stats.get("invalid_rows"):
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

    stats = analyze_file(CSV_FILE, collect_invalid=True)
    print_summary(stats)

    if ask_export():
        export_results(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())

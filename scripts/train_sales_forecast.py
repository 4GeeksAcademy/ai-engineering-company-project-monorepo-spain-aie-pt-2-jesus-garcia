"""Entrypoint reproducible del pronóstico de ventas de TrackFlow.

Uso:
    python -m scripts.train_sales_forecast
    python scripts/train_sales_forecast.py --output-dir docs/models-training-rag

Salidas (por defecto en ``docs/models-training-rag/``):
    figures/sales_forecast_test_2024_2025.png
    artifacts/predictions_test.csv
    artifacts/metrics.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sales_forecast.config import (  # noqa: E402
    DEFAULT_DATA_PATH,
    DEFAULT_OUTPUT_DIR,
    FIGURE_FILENAME,
    N_ESTIMATORS,
    SEED,
)
from scripts.sales_forecast.pipeline import run_forecast_pipeline  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrena y evalúa el pronóstico mensual de ingresos de TrackFlow."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="Ruta al CSV mensual de ventas.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directorio donde se escriben figura y artefactos.",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=N_ESTIMATORS,
        help="Número de árboles del Random Forest.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help="Semilla aleatoria (por defecto 42).",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Omite la generación de la figura.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = run_forecast_pipeline(
        data_path=args.data,
        output_dir=args.output_dir,
        n_estimators=args.n_estimators,
        seed=args.seed,
        make_plot=not args.no_plot,
    )

    split = results["split"]
    one_step = results["metrics"]["one_step"]
    recursive = results["metrics"]["recursive_24m"]

    print("=" * 72)
    print("TrackFlow · pronóstico de ingresos (Random Forest)")
    print("=" * 72)
    print(
        f"Split: train {split['train_start']} → {split['train_end']} "
        f"({split['train_rows']} meses) | test {split['test_start']} → "
        f"{split['test_end']} ({split['test_rows']} meses)"
    )
    print(f"Semilla: {results['experiment']['seed']}")
    print()
    print("Métricas one-step (24 meses de test)")
    print(f"  MSE     : {one_step['mse']:,.2f} EUR² "
          f"({one_step['mse_pct_of_train_mean_revenue']:.3f}% del ingreso medio)")
    print(f"  RMSE    : {one_step['rmse']:,.2f} EUR")
    print(f"  MAE     : {one_step['mae']:,.2f} EUR | MAPE: {one_step['mape_pct']:.2f}%")
    print(
        f"  PSI     : revenue {one_step['psi_revenue']['psi']:.4f} "
        f"({one_step['psi_revenue']['interpretation']}) | "
        f"yoy {one_step['psi_yoy_growth']['psi']:.4f} | "
        f"shipments {one_step['psi_shipments']['psi']:.4f}"
    )
    print(f"  Gini    : {one_step['gini']:.4f}")
    print(
        f"  K2      : {one_step['k2']['k2']:.4f} "
        f"(normalizado {one_step['k2']['k2_normalized']:.4f})"
    )
    print()
    print("Métricas recursivas 24 pasos (control de degradación)")
    print(
        f"  MSE     : {recursive['mse']:,.2f} EUR² | "
        f"MAPE: {recursive['mape_pct']:.2f}% | "
        f"Gini: {recursive['gini']:.4f} | "
        f"K2: {recursive['k2']['k2']:.4f}"
    )
    print()
    artifacts = [
        str(args.output_dir / "artifacts" / "metrics.json"),
        str(args.output_dir / "artifacts" / "predictions_test.csv"),
    ]
    if not args.no_plot:
        artifacts.append(
            str(args.output_dir / "figures" / FIGURE_FILENAME)
        )
    print("Artefactos: " + ", ".join(artifacts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

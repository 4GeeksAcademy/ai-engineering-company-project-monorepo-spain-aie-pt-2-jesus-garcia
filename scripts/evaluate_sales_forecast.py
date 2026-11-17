"""Evaluación temporal del pronóstico de ventas de TrackFlow.

Uso:
    python -m scripts.evaluate_sales_forecast
    python scripts/evaluate_sales_forecast.py --output-dir data/eval

Genera en ``data/eval/``:

* ``cv_results.json`` — folds, resumen media ± std, curva y A/B de regularización.
* ``cv_folds.csv`` — métricas por fold.
* ``learning_curve.csv`` — puntos de la curva de aprendizaje.
* ``learning_curve.png`` — curva train/validación (RMSE y MAE).

El test 2024-2025 no se usa: la validación cruzada se hace solo sobre el set de
entrenamiento (2018-01 → 2023-12, 72 filas efectivas).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sales_forecast.config import (  # noqa: E402
    CV_FOLDS_FILENAME,
    CV_GAP_MONTHS,
    CV_N_SPLITS,
    CV_RESULTS_FILENAME,
    CV_TEST_MONTHS,
    DEFAULT_DATA_PATH,
    EVAL_OUTPUT_DIR,
    FEATURE_COLUMNS,
    GROWTH_TARGET_COLUMN,
    LEARNING_CURVE_CSV_FILENAME,
    LEARNING_CURVE_FILENAME,
    LEARNING_CURVE_TRAIN_SIZES,
    LEARNING_CURVE_VALIDATION_MONTHS,
    MAX_FEATURES,
    MIN_SAMPLES_LEAF,
    N_ESTIMATORS,
    REGULARIZED_MIN_SAMPLES_LEAF,
    SEED,
    TARGET,
)
from scripts.sales_forecast.data import load_sales_data  # noqa: E402
from scripts.sales_forecast.features import (  # noqa: E402
    build_features,
    training_frame,
)
from scripts.sales_forecast.plots import plot_learning_curve  # noqa: E402
from scripts.sales_forecast.split import chronological_split  # noqa: E402
from scripts.sales_forecast.validation import (  # noqa: E402
    build_learning_curve,
    evaluate_reference_baselines,
    temporal_cross_validate,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evalúa el pronóstico de ventas con CV temporal."
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
        default=EVAL_OUTPUT_DIR,
        help="Directorio de artefactos de evaluación (por defecto data/eval).",
    )
    parser.add_argument(
        "--n-splits",
        type=int,
        default=CV_N_SPLITS,
        help="Número de folds temporales (mínimo 5).",
    )
    parser.add_argument(
        "--test-size",
        type=int,
        default=CV_TEST_MONTHS,
        help="Meses de validación por fold.",
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
        "--regularized-leaf",
        type=int,
        default=REGULARIZED_MIN_SAMPLES_LEAF,
        help="min_samples_leaf de la configuración regularizada del A/B.",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Omite la generación de la curva de aprendizaje.",
    )
    return parser.parse_args(argv)


def run_evaluation(
    *,
    data_path: str | Path = DEFAULT_DATA_PATH,
    output_dir: str | Path = EVAL_OUTPUT_DIR,
    n_splits: int = CV_N_SPLITS,
    test_size: int = CV_TEST_MONTHS,
    n_estimators: int = N_ESTIMATORS,
    seed: int = SEED,
    regularized_leaf: int = REGULARIZED_MIN_SAMPLES_LEAF,
    make_plot: bool = True,
) -> dict[str, object]:
    """Ejecuta CV, curva de aprendizaje y A/B de regularización."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_df, cleaning_report = load_sales_data(data_path)
    featured = build_features(raw_df)
    split = chronological_split(featured)
    train = training_frame(split.train).reset_index(drop=True)

    if train.empty:
        raise RuntimeError("No hay filas de entrenamiento con features completas")

    baseline = temporal_cross_validate(
        train,
        featured=featured,
        raw_df=raw_df,
        n_splits=n_splits,
        test_size=test_size,
        gap=CV_GAP_MONTHS,
        n_estimators=n_estimators,
        seed=seed,
        verify_causality=True,
    )
    regularized = temporal_cross_validate(
        train,
        featured=featured,
        raw_df=raw_df,
        n_splits=n_splits,
        test_size=test_size,
        gap=CV_GAP_MONTHS,
        n_estimators=n_estimators,
        seed=seed,
        model_params={"min_samples_leaf": regularized_leaf},
        verify_causality=False,
    )
    curve = build_learning_curve(
        train,
        featured=featured,
        validation_months=LEARNING_CURVE_VALIDATION_MONTHS,
        train_sizes=LEARNING_CURVE_TRAIN_SIZES,
        n_estimators=n_estimators,
        seed=seed,
    )
    baselines = evaluate_reference_baselines(
        train,
        featured=featured,
        n_splits=n_splits,
        test_size=test_size,
        gap=CV_GAP_MONTHS,
    )

    results: dict[str, object] = {
        "experiment": {
            "target": TARGET,
            "learned_target": GROWTH_TARGET_COLUMN,
            "model": "RandomForestRegressor",
            "n_estimators": n_estimators,
            "random_state": seed,
            "min_samples_leaf": MIN_SAMPLES_LEAF,
            "max_features": MAX_FEATURES,
            "features": list(FEATURE_COLUMNS),
            "holdout_test": "2024-01 → 2025-12 (no usado en esta evaluación)",
        },
        "dataset": cleaning_report,
        "split": split.summary(),
        "effective_training": {
            "rows": int(len(train)),
            "first_month": train["month"].min().strftime("%Y-%m"),
            "last_month": train["month"].max().strftime("%Y-%m"),
            "rows_dropped_for_lags": int(len(split.train) - len(train)),
            "mean_revenue_eur": float(train[TARGET].mean()),
        },
        "cv": {
            **baseline["cv"],
            "folds": baseline["folds"],
            "summary": baseline["summary"],
            "leakage_checks": baseline["leakage_checks"],
        },
        "learning_curve": {
            "validation_months": LEARNING_CURVE_VALIDATION_MONTHS,
            "train_sizes": list(LEARNING_CURVE_TRAIN_SIZES),
            "points": curve,
        },
        "regularization_experiment": {
            "change": {"min_samples_leaf": regularized_leaf},
            "folds": regularized["folds"],
            "summary": regularized["summary"],
        },
        "reference_baselines": baselines,
        "artifacts": {
            "cv_results": CV_RESULTS_FILENAME,
            "cv_folds": CV_FOLDS_FILENAME,
            "learning_curve_csv": LEARNING_CURVE_CSV_FILENAME,
            "learning_curve_png": LEARNING_CURVE_FILENAME if make_plot else None,
        },
    }

    _write_json(results, output_dir / CV_RESULTS_FILENAME)
    _folds_to_frame(baseline["folds"]).to_csv(
        output_dir / CV_FOLDS_FILENAME, index=False
    )
    _curve_to_frame(curve).to_csv(
        output_dir / LEARNING_CURVE_CSV_FILENAME, index=False
    )

    if make_plot:
        plot_learning_curve(
            points=curve,
            output_path=output_dir / LEARNING_CURVE_FILENAME,
        )

    return results


def _folds_to_frame(folds: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for fold in folds:
        train = fold["train"]
        validation = fold["validation"]
        rows.append(
            {
                "fold": fold["fold"],
                "train_start": fold["train_start"],
                "train_end": fold["train_end"],
                "validation_start": fold["validation_start"],
                "validation_end": fold["validation_end"],
                "n_train": fold["n_train"],
                "n_validation": fold["n_validation"],
                "train_mae_eur": train["mae_eur"],
                "train_rmse_eur": train["rmse_eur"],
                "train_mape_pct": train["mape_pct"],
                "validation_mae_eur": validation["mae_eur"],
                "validation_rmse_eur": validation["rmse_eur"],
                "validation_mape_pct": validation["mape_pct"],
            }
        )
    return pd.DataFrame(rows)


def _curve_to_frame(points: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for point in points:
        train = point["train"]
        validation = point["validation"]
        rows.append(
            {
                "n_train_rows": point["n_train_rows"],
                "train_start": point["train_start"],
                "train_end": point["train_end"],
                "validation_start": point["validation_start"],
                "validation_end": point["validation_end"],
                "train_mae_eur": train["mae_eur"],
                "train_rmse_eur": train["rmse_eur"],
                "train_mape_pct": train["mape_pct"],
                "validation_mae_eur": validation["mae_eur"],
                "validation_rmse_eur": validation["rmse_eur"],
                "validation_mape_pct": validation["mape_pct"],
            }
        )
    return pd.DataFrame(rows)


def _write_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_jsonable(payload), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m")
    return value


def _print_summary(results: dict[str, object]) -> None:
    cv = results["cv"]
    summary = cv["summary"]
    print("=" * 78)
    print("TrackFlow · evaluación temporal del pronóstico de ingresos")
    print("=" * 78)
    print(
        f"CV: {cv['strategy']} · {cv['n_splits']} folds × "
        f"{cv['test_size_months']} meses · shuffle={cv['shuffle']} · "
        f"gap={cv['gap_months']}"
    )
    print(
        f"Train efectivo: {results['effective_training']['rows']} filas "
        f"({results['effective_training']['first_month']} → "
        f"{results['effective_training']['last_month']}) | "
        f"test 2024-2025 NO usado"
    )
    print()
    print(f"{'Fold':<5}{'Train':<18}{'Validación':<18}{'MAE val':>12}{'RMSE val':>12}{'MAPE val':>10}")
    for fold in cv["folds"]:
        print(
            f"{fold['fold']:<5}"
            f"{fold['train_start'] + '→' + fold['train_end']:<18}"
            f"{fold['validation_start'] + '→' + fold['validation_end']:<18}"
            f"{fold['validation']['mae_eur']:>12,.0f}"
            f"{fold['validation']['rmse_eur']:>12,.0f}"
            f"{fold['validation']['mape_pct']:>9.2f}%"
        )
    print()
    for mode, label in (("train", "Entrenamiento"), ("validation", "Validación")):
        mae = summary[mode]["mae_eur"]
        rmse = summary[mode]["rmse_eur"]
        mape = summary[mode]["mape_pct"]
        print(
            f"{label:<14} MAE {mae['mean']:,.0f} ± {mae['std']:,.0f} EUR | "
            f"RMSE {rmse['mean']:,.0f} ± {rmse['std']:,.0f} EUR | "
            f"MAPE {mape['mean']:.2f} ± {mape['std']:.2f}%"
        )
    print()
    print("Curva de aprendizaje (validación fija 2023):")
    for point in results["learning_curve"]["points"]:
        print(
            f"  n={point['n_train_rows']:>2} meses | "
            f"train MAPE {point['train']['mape_pct']:.2f}% | "
            f"val MAPE {point['validation']['mape_pct']:.2f}% | "
            f"val RMSE {point['validation']['rmse_eur']:,.0f} EUR"
        )
    regularized = results["regularization_experiment"]
    base_rmse = summary["validation"]["rmse_eur"]
    reg_rmse = regularized["summary"]["validation"]["rmse_eur"]
    print()
    print(
        f"A/B regularización (min_samples_leaf="
        f"{regularized['change']['min_samples_leaf']}): "
        f"RMSE val {reg_rmse['mean']:,.0f} ± {reg_rmse['std']:,.0f} EUR "
        f"(baseline {base_rmse['mean']:,.0f} ± {base_rmse['std']:,.0f})"
    )
    print()
    print("Artefactos en data/eval/: cv_results.json, cv_folds.csv, "
          "learning_curve.csv, learning_curve.png")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = run_evaluation(
        data_path=args.data,
        output_dir=args.output_dir,
        n_splits=args.n_splits,
        test_size=args.test_size,
        n_estimators=args.n_estimators,
        seed=args.seed,
        regularized_leaf=args.regularized_leaf,
        make_plot=not args.no_plot,
    )
    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

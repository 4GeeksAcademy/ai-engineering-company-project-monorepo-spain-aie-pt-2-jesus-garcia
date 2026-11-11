"""Orquestador del experimento de pronóstico de ventas de TrackFlow.

Flujo: cargar y limpiar → features causales → split 8/2 → entrenar Random
Forest → predecir one-step y recursivo → calcular MSE/PSI/Gini/K2 → guardar
figura, predicciones y métricas en ``docs/models-training-rag/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    BASE_LAG_MONTHS,
    DEFAULT_DATA_PATH,
    DEFAULT_OUTPUT_DIR,
    FEATURE_COLUMNS,
    FIGURE_FILENAME,
    GROWTH_TARGET_COLUMN,
    INTERVAL_QUANTILES,
    K2_BINS,
    MARKET,
    MAX_FEATURES,
    METRICS_FILENAME,
    MIN_SAMPLES_LEAF,
    N_ESTIMATORS,
    OUTER_INTERVAL_QUANTILES,
    PREDICTIONS_FILENAME,
    SEED,
    TARGET,
)
from .data import load_sales_data
from .features import build_features, training_frame
from .metrics import (
    gini_accuracy_ratio,
    k2_score,
    population_stability_index,
    regression_metrics,
)
from .model import (
    build_model,
    feature_importances,
    fit_forecaster,
    forecast_interval,
    point_forecast,
    recursive_forecast,
)
from .plots import plot_forecast
from .split import chronological_split


def run_forecast_pipeline(
    data_path: str | Path = DEFAULT_DATA_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    n_estimators: int = N_ESTIMATORS,
    seed: int = SEED,
    make_plot: bool = True,
) -> dict[str, object]:
    """Ejecuta el experimento completo y devuelve el resumen de métricas."""

    output_dir = Path(output_dir)
    figures_dir = output_dir / "figures"
    artifacts_dir = output_dir / "artifacts"

    raw_df, cleaning_report = load_sales_data(data_path)
    featured = build_features(raw_df)
    split = chronological_split(featured)

    train = training_frame(split.train)
    if train.empty:
        raise RuntimeError("No hay filas de entrenamiento con features completas")
    test = split.test
    if test[list(FEATURE_COLUMNS)].isna().any().any():
        raise RuntimeError(
            "El conjunto de test tiene features incompletas; revisa el split"
        )

    # --- Entrenamiento ----------------------------------------------------
    model = build_model(n_estimators=n_estimators, random_state=seed)
    fit_forecaster(model, train, train[GROWTH_TARGET_COLUMN])

    test_features = test.copy()
    base_revenue = (
        featured[TARGET].shift(BASE_LAG_MONTHS).iloc[len(split.train) :].to_numpy()
    )
    one_step_pred = point_forecast(model, test_features, base_revenue)
    interval = forecast_interval(
        model,
        test_features,
        base_revenue,
        quantiles=tuple(
            sorted(set(INTERVAL_QUANTILES + OUTER_INTERVAL_QUANTILES))
        ),
    )
    recursive_pred = recursive_forecast(
        model,
        featured,
        start_index=len(split.train),
        horizon=len(test),
    )

    train_reference_mean = float(train[TARGET].mean())
    y_true = test[TARGET].to_numpy(dtype=float)

    one_step_metrics = _mode_metrics(
        y_true,
        one_step_pred,
        raw_df=raw_df,
        train=train,
        test=test,
        reference_mean=train_reference_mean,
    )
    recursive_metrics = _mode_metrics(
        y_true,
        recursive_pred,
        raw_df=raw_df,
        train=train,
        test=test,
        reference_mean=train_reference_mean,
        include_distribution_shift=False,
    )
    distribution_shift = _distribution_shift(raw_df, train, test)

    predictions = _build_predictions_frame(
        test=test,
        one_step_pred=one_step_pred,
        recursive_pred=recursive_pred,
        interval=interval,
    )

    results: dict[str, object] = {
        "experiment": {
            "seed": seed,
            "market": MARKET,
            "target": TARGET,
            "learned_target": GROWTH_TARGET_COLUMN,
            "base_lag_months": BASE_LAG_MONTHS,
            "model": "RandomForestRegressor",
            "model_params": {
                "n_estimators": n_estimators,
                "min_samples_leaf": MIN_SAMPLES_LEAF,
                "max_features": MAX_FEATURES,
                "random_state": seed,
                "bootstrap": True,
            },
            "features": list(FEATURE_COLUMNS),
            "feature_importances": feature_importances(model),
            "k2_bins": K2_BINS,
        },
        "dataset": cleaning_report,
        "split": split.summary(),
        "training": {
            "rows_used": int(len(train)),
            "rows_dropped_for_lags": int(len(split.train) - len(train)),
        },
        "metrics": {
            "one_step": one_step_metrics,
            "recursive_24m": recursive_metrics,
        },
        "distribution_shift": distribution_shift,
        "artifacts": {
            "predictions": str(
                (artifacts_dir / PREDICTIONS_FILENAME).relative_to(output_dir)
            ),
            "metrics": str((artifacts_dir / METRICS_FILENAME).relative_to(output_dir)),
            "figure": str((figures_dir / FIGURE_FILENAME).relative_to(output_dir)),
        },
    }

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(artifacts_dir / PREDICTIONS_FILENAME, index=False)
    _write_json(results, artifacts_dir / METRICS_FILENAME)

    if make_plot:
        context = split.train.tail(12).copy()
        plot_path = plot_forecast(
            context=context,
            test_predictions=predictions,
            metrics={"one_step": one_step_metrics},
            output_path=figures_dir / FIGURE_FILENAME,
        )
        results["artifacts"]["figure"] = str(plot_path.relative_to(output_dir))

    return results


def _mode_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    raw_df: pd.DataFrame,
    train: pd.DataFrame,
    test: pd.DataFrame,
    reference_mean: float,
    include_distribution_shift: bool = True,
) -> dict[str, object]:
    """Calcula todas las métricas de un modo de evaluación sobre test."""

    metrics: dict[str, object] = regression_metrics(
        y_true, y_pred, reference_mean=reference_mean
    )
    metrics["gini"] = gini_accuracy_ratio(y_true, y_pred)
    metrics["k2"] = k2_score(y_true, y_pred)

    if include_distribution_shift:
        shift = _distribution_shift(raw_df, train, test)
        metrics["psi_revenue"] = shift["revenue_eur"]
        metrics["psi_yoy_growth"] = shift["yoy_growth"]
        metrics["psi_shipments"] = shift["shipments_processed"]

    return metrics


def _distribution_shift(
    raw_df: pd.DataFrame,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    """PSI de las variables relevantes entre train y test (diagnóstico)."""

    train_months = set(pd.to_datetime(train["month"]))
    test_months = set(pd.to_datetime(test["month"]))
    months = pd.to_datetime(raw_df["month"])
    train_mask = months.isin(train_months).to_numpy()
    test_mask = months.isin(test_months).to_numpy()

    yoy_growth = raw_df[TARGET].pct_change(12) * 100
    yoy_train = yoy_growth[train_mask].dropna().to_numpy()
    yoy_test = yoy_growth[test_mask].dropna().to_numpy()

    return {
        "revenue_eur": population_stability_index(
            raw_df.loc[train_mask, TARGET].to_numpy(),
            raw_df.loc[test_mask, TARGET].to_numpy(),
        ),
        "yoy_growth": population_stability_index(yoy_train, yoy_test),
        "shipments_processed": population_stability_index(
            raw_df.loc[train_mask, "shipments_processed"].to_numpy(),
            raw_df.loc[test_mask, "shipments_processed"].to_numpy(),
        ),
    }


def _build_predictions_frame(
    *,
    test: pd.DataFrame,
    one_step_pred: np.ndarray,
    recursive_pred: np.ndarray,
    interval: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Tabla de test con reales, predicciones y bandas para el CSV/figura."""

    predictions = pd.DataFrame(
        {
            "month": test["month"].dt.strftime("%Y-%m"),
            "revenue_eur": test[TARGET].to_numpy(dtype=float),
            "prediction_eur": one_step_pred,
            "lower_eur": interval["q10"],
            "upper_eur": interval["q90"],
            "lower_outer_eur": interval["q05"],
            "upper_outer_eur": interval["q95"],
            "recursive_prediction_eur": recursive_pred,
        }
    )
    predictions["residual_pct"] = (
        (predictions["revenue_eur"] - predictions["prediction_eur"])
        / predictions["revenue_eur"]
        * 100
    )
    return predictions.round(2)


def _write_json(payload: dict[str, object], path: Path) -> None:
    """Serializa numpy/pandas a JSON legible y determinista."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_jsonable(payload), handle, indent=2, ensure_ascii=False, sort_keys=False)
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
    return value

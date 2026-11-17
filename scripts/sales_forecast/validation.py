"""Validación cruzada temporal y curva de aprendizaje del pronóstico de ventas.

El objetivo de este módulo es medir la capacidad de generalización del modelo
**sin tocar el test 2024-2025** y sin romper el orden cronológico. La unidad de
evaluación es la fila mensual del set de entrenamiento (2018-01 → 2023-12), que
es donde las features de lag/rolling están completas.

Reglas que se verifican en tiempo de ejecución y en los tests:

* ``TimeSeriesSplit`` nunca baraja: cada fold entrena con un prefijo y valida
  con el bloque inmediatamente posterior.
* Ninguna feature de una fila de train puede depender de los meses del bloque
  de validación ni de folds futuros. Para comprobarlo se reconstruyen las
  features truncando la serie en las fronteras de cada fold y se comparan.
* La predicción es one-step: la base de ingresos de ``t-12`` y los lags hasta
  ``t-1`` son datos reales conocidos. No se realimentan predicciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from .config import (
    BASE_LAG_MONTHS,
    CV_GAP_MONTHS,
    CV_N_SPLITS,
    CV_TEST_MONTHS,
    FEATURE_COLUMNS,
    GROWTH_TARGET_COLUMN,
    LEARNING_CURVE_TRAIN_SIZES,
    LEARNING_CURVE_VALIDATION_MONTHS,
    N_ESTIMATORS,
    SEED,
    TARGET,
)
from .features import build_features
from .metrics import regression_metrics
from .model import build_model, fit_forecaster, point_forecast

_TRAINING_COLUMNS = (
    "month",
    TARGET,
    GROWTH_TARGET_COLUMN,
    *FEATURE_COLUMNS,
)


@dataclass(frozen=True)
class TemporalFold:
    """Un fold cronológico: prefijo de entrenamiento + bloque de validación."""

    fold_id: int
    train_idx: np.ndarray
    validation_idx: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp

    @property
    def n_train(self) -> int:
        return int(self.train_idx.size)

    @property
    def n_validation(self) -> int:
        return int(self.validation_idx.size)

    def summary(self) -> dict[str, object]:
        return {
            "fold": self.fold_id,
            "train_start": self.train_start.strftime("%Y-%m"),
            "train_end": self.train_end.strftime("%Y-%m"),
            "validation_start": self.validation_start.strftime("%Y-%m"),
            "validation_end": self.validation_end.strftime("%Y-%m"),
            "n_train": self.n_train,
            "n_validation": self.n_validation,
        }


def build_time_series_folds(
    frame: pd.DataFrame,
    *,
    n_splits: int = CV_N_SPLITS,
    test_size: int = CV_TEST_MONTHS,
    gap: int = CV_GAP_MONTHS,
) -> list[TemporalFold]:
    """Construye folds con ``TimeSeriesSplit`` y valida su orden cronológico."""

    _require_columns(frame, ("month",), "el set de entrenamiento")
    if n_splits < 5:
        raise ValueError(
            f"Se exigen al menos 5 folds temporales; se recibieron {n_splits}"
        )
    if test_size <= 0:
        raise ValueError("El tamaño de validación debe ser positivo")

    ordered = frame.sort_values("month").reset_index(drop=True)
    if not ordered["month"].is_monotonic_increasing:
        raise ValueError("Las filas deben estar ordenadas por 'month'")
    if ordered["month"].duplicated().any():
        raise ValueError("Hay meses duplicados en el set de entrenamiento")
    if len(ordered) < (n_splits + 1) * test_size:
        raise ValueError(
            f"El set de entrenamiento tiene {len(ordered)} filas; no alcanza "
            f"para {n_splits} folds de {test_size} meses"
        )

    splitter = TimeSeriesSplit(
        n_splits=n_splits,
        test_size=test_size,
        gap=gap,
    )
    folds: list[TemporalFold] = []
    for fold_id, (train_idx, validation_idx) in enumerate(
        splitter.split(ordered), start=1
    ):
        train_idx = np.asarray(train_idx, dtype=int)
        validation_idx = np.asarray(validation_idx, dtype=int)
        folds.append(
            TemporalFold(
                fold_id=fold_id,
                train_idx=train_idx,
                validation_idx=validation_idx,
                train_start=ordered.loc[train_idx[0], "month"],
                train_end=ordered.loc[train_idx[-1], "month"],
                validation_start=ordered.loc[validation_idx[0], "month"],
                validation_end=ordered.loc[validation_idx[-1], "month"],
            )
        )

    assert_temporal_folds(folds)
    return folds


def assert_temporal_folds(folds: list[TemporalFold]) -> None:
    """Falla si los folds se solapan, se barajan o rompen el orden temporal."""

    if len(folds) < 5:
        raise ValueError(f"Se exigen al menos 5 folds; hay {len(folds)}")

    first_train_min = int(folds[0].train_idx.min())
    for fold in folds:
        _assert_sorted_unique(fold.train_idx, f"train del fold {fold.fold_id}")
        _assert_sorted_unique(
            fold.validation_idx, f"validación del fold {fold.fold_id}"
        )
        if fold.train_idx.max() >= fold.validation_idx.min():
            raise ValueError(
                f"El fold {fold.fold_id} mezcla train y validación: "
                f"train termina en {fold.train_idx.max()} y validación empieza "
                f"en {fold.validation_idx.min()}"
            )
        if np.intersect1d(fold.train_idx, fold.validation_idx).size:
            raise ValueError(f"El fold {fold.fold_id} tiene índices compartidos")
        if fold.train_end >= fold.validation_start:
            raise ValueError(
                f"El fold {fold.fold_id} no respeta el orden de fechas: "
                f"{fold.train_end:%Y-%m} >= {fold.validation_start:%Y-%m}"
            )

    for previous, current in zip(folds, folds[1:]):
        if current.validation_idx.min() <= previous.validation_idx.max():
            raise ValueError(
                "Los bloques de validación se solapan o están desordenados "
                f"(fold {previous.fold_id} → {current.fold_id})"
            )
        if current.train_idx.min() != first_train_min:
            raise ValueError(
                "La ventana de entrenamiento debe ser expansiva y empezar en el "
                f"mismo índice (fold {current.fold_id})"
            )
        if not set(previous.train_idx.tolist()).issubset(
            set(current.train_idx.tolist())
        ):
            raise ValueError(
                f"El fold {current.fold_id} no contiene todo el train del fold "
                f"{previous.fold_id}: la ventana no es expansiva"
            )
        if current.train_idx.max() <= previous.train_idx.max():
            raise ValueError(
                f"El fold {current.fold_id} no añade historia respecto al "
                f"fold {previous.fold_id}"
            )

    concatenated = np.concatenate([fold.validation_idx for fold in folds])
    if not np.all(np.diff(concatenated) > 0):
        raise ValueError(
            "Los índices de validación no están estrictamente ordenados: "
            "un fold posterior aparece antes que uno anterior"
        )


def assert_fold_features_are_causal(
    raw_df: pd.DataFrame,
    featured: pd.DataFrame,
    fold: TemporalFold,
) -> dict[str, object]:
    """Comprueba que las features del fold no miran a validación ni al futuro.

    Se reconstruyen las features con la serie truncada en dos fronteras:

    1. ``validation_end``: todo lo que el fold puede ver en el peor caso.
    2. ``train_end``: lo que puede ver el entrenamiento, sin el bloque de
       validación.

    Además, para cada mes de validación se construye la fila de features usando
    únicamente datos hasta ``t-1``. Si alguna feature de lag/rolling usara el
    mes actual o el futuro, la comparación fallaría.
    """

    _require_columns(raw_df, ("month", TARGET), "el dataset raw")
    _require_columns(featured, _TRAINING_COLUMNS, "el dataset con features")

    columns = (*FEATURE_COLUMNS, GROWTH_TARGET_COLUMN)

    truncated_at_validation = build_features(
        raw_df.loc[raw_df["month"] <= fold.validation_end].copy()
    )
    _compare_feature_slice(
        truncated_at_validation,
        featured,
        end=fold.validation_end,
        columns=columns,
        label=f"fold {fold.fold_id} (hasta validation_end)",
    )

    truncated_at_train = build_features(
        raw_df.loc[raw_df["month"] <= fold.train_end].copy()
    )
    _compare_feature_slice(
        truncated_at_train,
        featured,
        end=fold.train_end,
        columns=columns,
        label=f"fold {fold.fold_id} (hasta train_end)",
    )

    checked_months = 0
    validation_months = featured.loc[
        (featured["month"] >= fold.validation_start)
        & (featured["month"] <= fold.validation_end),
        "month",
    ]
    for month in validation_months:
        _assert_month_features_use_only_past(raw_df, featured, month)
        checked_months += 1

    return {
        "fold": fold.fold_id,
        "features_until_validation_end_match_full_series": True,
        "training_features_match_truncation_at_train_end": True,
        "validation_rows_checked_against_past": checked_months,
        "validation_rows_use_only_past": True,
    }


def temporal_cross_validate(
    train_frame: pd.DataFrame,
    *,
    featured: pd.DataFrame,
    raw_df: pd.DataFrame | None = None,
    n_splits: int = CV_N_SPLITS,
    test_size: int = CV_TEST_MONTHS,
    gap: int = CV_GAP_MONTHS,
    n_estimators: int = N_ESTIMATORS,
    seed: int = SEED,
    model_params: Mapping[str, object] | None = None,
    verify_causality: bool = True,
) -> dict[str, object]:
    """Evalúa el modelo con CV temporal y devuelve métricas por fold y resumen."""

    _require_columns(train_frame, _TRAINING_COLUMNS, "el set de entrenamiento")
    _require_columns(featured, _TRAINING_COLUMNS, "el dataset con features")

    train = train_frame.sort_values("month").reset_index(drop=True)
    folds = build_time_series_folds(
        train,
        n_splits=n_splits,
        test_size=test_size,
        gap=gap,
    )
    base_revenue = _base_revenue_for(train, featured)
    reference_mean = float(train[TARGET].mean())
    params = dict(model_params or {})

    records: list[dict[str, object]] = []
    leakage_checks: dict[str, object] = {}

    for fold in folds:
        if verify_causality:
            if raw_df is None:
                raise ValueError(
                    "verify_causality=True requiere raw_df para reconstruir "
                    "features en las fronteras de cada fold"
                )
            leakage_checks[str(fold.fold_id)] = assert_fold_features_are_causal(
                raw_df, featured, fold
            )

        train_rows = train.iloc[fold.train_idx]
        validation_rows = train.iloc[fold.validation_idx]
        model = build_model(
            n_estimators=n_estimators,
            random_state=seed,
            **params,
        )
        fit_forecaster(
            model,
            train_rows,
            train_rows[GROWTH_TARGET_COLUMN],
        )

        train_prediction = point_forecast(
            model,
            train_rows,
            base_revenue[fold.train_idx],
        )
        validation_prediction = point_forecast(
            model,
            validation_rows,
            base_revenue[fold.validation_idx],
        )

        record = {
            **fold.summary(),
            "train": _fold_metrics(
                train_rows[TARGET].to_numpy(dtype=float),
                train_prediction,
                reference_mean,
            ),
            "validation": _fold_metrics(
                validation_rows[TARGET].to_numpy(dtype=float),
                validation_prediction,
                reference_mean,
            ),
        }
        records.append(record)

    return {
        "cv": {
            "strategy": "TimeSeriesSplit",
            "n_splits": n_splits,
            "test_size_months": test_size,
            "gap_months": gap,
            "shuffle": False,
            "reference_mean_revenue_eur": reference_mean,
        },
        "model_params": {
            "n_estimators": n_estimators,
            "random_state": seed,
            **params,
        },
        "folds": records,
        "summary": _summarize_folds(records),
        "leakage_checks": leakage_checks,
    }


def build_learning_curve(
    train_frame: pd.DataFrame,
    *,
    featured: pd.DataFrame,
    validation_months: int = LEARNING_CURVE_VALIDATION_MONTHS,
    train_sizes: tuple[int, ...] = LEARNING_CURVE_TRAIN_SIZES,
    n_estimators: int = N_ESTIMATORS,
    seed: int = SEED,
    model_params: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Curva de aprendizaje con validación fija y ventana expansiva hacia atrás.

    La validación es el último bloque de ``validation_months`` del train (2023).
    Para cada tamaño ``n`` se entrena con los ``n`` meses inmediatamente
    anteriores a ese bloque. Así el train siempre termina antes de la validación
    y lo único que cambia entre puntos es cuánta historia se añade.
    """

    _require_columns(train_frame, _TRAINING_COLUMNS, "el set de entrenamiento")
    _require_columns(featured, _TRAINING_COLUMNS, "el dataset con features")

    train = train_frame.sort_values("month").reset_index(drop=True)
    if validation_months <= 0 or validation_months >= len(train):
        raise ValueError(
            f"validation_months={validation_months} no es válido para "
            f"{len(train)} filas"
        )

    validation_start_index = len(train) - validation_months
    validation_idx = np.arange(validation_start_index, len(train))
    validation_rows = train.iloc[validation_idx]
    base_revenue = _base_revenue_for(train, featured)
    reference_mean = float(train[TARGET].mean())
    params = dict(model_params or {})

    sizes = tuple(sorted(set(int(size) for size in train_sizes)))
    if not sizes:
        raise ValueError("La curva de aprendizaje necesita al menos un tamaño")
    if any(size <= 0 for size in sizes):
        raise ValueError("Los tamaños de entrenamiento deben ser positivos")

    points: list[dict[str, object]] = []
    for size in sizes:
        if size > validation_start_index:
            raise ValueError(
                f"El tamaño {size} no cabe antes de la validación fija "
                f"(índice {validation_start_index})"
            )
        train_idx = np.arange(validation_start_index - size, validation_start_index)
        train_rows = train.iloc[train_idx]

        model = build_model(
            n_estimators=n_estimators,
            random_state=seed,
            **params,
        )
        fit_forecaster(model, train_rows, train_rows[GROWTH_TARGET_COLUMN])

        train_prediction = point_forecast(
            model,
            train_rows,
            base_revenue[train_idx],
        )
        validation_prediction = point_forecast(
            model,
            validation_rows,
            base_revenue[validation_idx],
        )

        points.append(
            {
                "n_train_rows": int(size),
                "train_start": train_rows["month"].min().strftime("%Y-%m"),
                "train_end": train_rows["month"].max().strftime("%Y-%m"),
                "validation_start": validation_rows["month"].min().strftime("%Y-%m"),
                "validation_end": validation_rows["month"].max().strftime("%Y-%m"),
                "train": _fold_metrics(
                    train_rows[TARGET].to_numpy(dtype=float),
                    train_prediction,
                    reference_mean,
                ),
                "validation": _fold_metrics(
                    validation_rows[TARGET].to_numpy(dtype=float),
                    validation_prediction,
                    reference_mean,
                ),
            }
        )

    return points


def evaluate_reference_baselines(
    train_frame: pd.DataFrame,
    *,
    featured: pd.DataFrame,
    n_splits: int = CV_N_SPLITS,
    test_size: int = CV_TEST_MONTHS,
    gap: int = CV_GAP_MONTHS,
) -> dict[str, dict[str, object]]:
    """Métricas de referencias ingenuas sobre los mismos folds de validación."""

    _require_columns(train_frame, _TRAINING_COLUMNS, "el set de entrenamiento")
    _require_columns(featured, _TRAINING_COLUMNS, "el dataset con features")

    train = train_frame.sort_values("month").reset_index(drop=True)
    folds = build_time_series_folds(
        train,
        n_splits=n_splits,
        test_size=test_size,
        gap=gap,
    )
    base_revenue = _base_revenue_for(train, featured)
    reference_mean = float(train[TARGET].mean())
    growth = train[GROWTH_TARGET_COLUMN].to_numpy(dtype=float)
    revenue = train[TARGET].to_numpy(dtype=float)

    predictions = {
        "zero_growth": np.zeros_like(growth),
        "lag_12": pd.Series(growth).shift(BASE_LAG_MONTHS).to_numpy(),
        "rolling_mean_3": pd.Series(growth)
        .shift(1)
        .rolling(3, min_periods=1)
        .mean()
        .to_numpy(),
    }

    baseline_metrics: dict[str, dict[str, object]] = {}
    for name, predicted_growth in predictions.items():
        records = []
        for fold in folds:
            indices = fold.validation_idx
            predicted_revenue = (
                np.exp(predicted_growth[indices]) * base_revenue[indices]
            )
            records.append(
                _fold_metrics(
                    revenue[indices],
                    predicted_revenue,
                    reference_mean,
                )
            )
        baseline_metrics[name] = _summarize_metric_records(records)
    return baseline_metrics


def _fold_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    reference_mean: float,
) -> dict[str, float]:
    """MAE/RMSE/MAPE (y MSE como apoyo) en EUR sobre un conjunto."""

    metrics = regression_metrics(y_true, y_pred, reference_mean=reference_mean)
    return {
        "mse_eur2": float(metrics["mse"]),
        "rmse_eur": float(metrics["rmse"]),
        "mae_eur": float(metrics["mae"]),
        "mape_pct": float(metrics["mape_pct"]),
    }


def _summarize_metric_records(
    records: list[dict[str, float]],
) -> dict[str, object]:
    """Media ± desviación estándar (ddof=1) de una lista de métricas."""

    if not records:
        raise ValueError("No hay métricas que resumir")

    summary: dict[str, object] = {}
    for metric in ("mae_eur", "rmse_eur", "mape_pct", "mse_eur2"):
        values = np.array(
            [float(record[metric]) for record in records], dtype=float
        )
        summary[metric] = {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=1)) if values.size > 1 else 0.0,
            "min": float(values.min()),
            "max": float(values.max()),
        }
    return summary


def _summarize_folds(records: list[dict[str, object]]) -> dict[str, object]:
    """Media ± desviación estándar (ddof=1) de las métricas por fold."""

    if not records:
        raise ValueError("No hay folds que resumir")

    return {
        "n_folds": len(records),
        "train": _summarize_metric_records(
            [record["train"] for record in records]
        ),
        "validation": _summarize_metric_records(
            [record["validation"] for record in records]
        ),
    }


def _base_revenue_for(
    frame: pd.DataFrame,
    featured: pd.DataFrame,
) -> np.ndarray:
    """Ingresos reales de ``t-12`` para cada fila de ``frame`` (base conocida)."""

    revenue_by_month = featured.set_index("month")[TARGET]
    if revenue_by_month.index.has_duplicates:
        raise ValueError("Hay meses duplicados en el dataset con features")

    base_months = pd.to_datetime(frame["month"]) - pd.DateOffset(
        months=BASE_LAG_MONTHS
    )
    base = base_months.map(revenue_by_month)
    missing = frame.loc[base.isna(), "month"]
    if not missing.empty:
        sample = [month.strftime("%Y-%m") for month in missing.head(5)]
        raise ValueError(
            "No hay ingresos de t-12 para construir la base: " + ", ".join(sample)
        )
    if (base <= 0).any():
        raise ValueError("La base de ingresos de t-12 debe ser positiva")
    return base.to_numpy(dtype=float)


def _compare_feature_slice(
    truncated: pd.DataFrame,
    full: pd.DataFrame,
    *,
    end: pd.Timestamp,
    columns: tuple[str, ...],
    label: str,
) -> None:
    """Compara features reconstruidas y completas hasta una fecha."""

    left = (
        truncated.loc[truncated["month"] <= end]
        .set_index("month")[list(columns)]
        .sort_index()
    )
    right = (
        full.loc[full["month"] <= end]
        .set_index("month")[list(columns)]
        .sort_index()
    )
    if not left.index.equals(right.index):
        raise ValueError(
            f"Fuga de información en {label}: los meses reconstruidos no "
            "coinciden con la serie completa"
        )
    try:
        np.testing.assert_allclose(
            left.to_numpy(dtype=float),
            right.to_numpy(dtype=float),
            rtol=0,
            atol=0,
            equal_nan=True,
        )
    except AssertionError as exc:
        raise ValueError(
            f"Fuga de información en {label}: una feature de lag/rolling cambió "
            f"al truncar la serie en {end:%Y-%m}"
        ) from exc


def _assert_month_features_use_only_past(
    raw_df: pd.DataFrame,
    featured: pd.DataFrame,
    month: pd.Timestamp,
) -> None:
    """Comprueba que la fila de features de ``month`` solo usa meses < month."""

    past = raw_df.loc[raw_df["month"] < month].copy()
    placeholder = {column: np.nan for column in past.columns}
    placeholder["month"] = month
    extended = pd.concat(
        [past, pd.DataFrame([placeholder])],
        ignore_index=True,
    )
    computed = build_features(extended)
    computed_row = computed.loc[
        computed["month"] == month, list(FEATURE_COLUMNS)
    ]
    full_row = featured.loc[
        featured["month"] == month, list(FEATURE_COLUMNS)
    ]
    if computed_row.empty or full_row.empty:
        raise ValueError(f"No se pudo reconstruir la fila de features de {month:%Y-%m}")

    try:
        np.testing.assert_allclose(
            computed_row.to_numpy(dtype=float),
            full_row.to_numpy(dtype=float),
            rtol=0,
            atol=0,
            equal_nan=True,
        )
    except AssertionError as exc:
        raise ValueError(
            f"Fuga de información en la fila {month:%Y-%m}: las features usan "
            "el mes actual o el futuro"
        ) from exc


def _assert_sorted_unique(indices: np.ndarray, label: str) -> None:
    if indices.size == 0:
        raise ValueError(f"Los índices de {label} están vacíos")
    if not np.all(np.diff(indices) > 0):
        raise ValueError(
            f"Los índices de {label} no son estrictamente crecientes: "
            "hay desorden, duplicados o shuffle"
        )


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    name: str,
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Faltan columnas en {name}: {missing}")

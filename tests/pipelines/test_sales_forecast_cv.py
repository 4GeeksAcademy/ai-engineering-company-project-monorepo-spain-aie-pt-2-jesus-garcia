"""Tests de la validación cruzada temporal del pronóstico de ventas.

El caso central comprueba que ``TimeSeriesSplit`` no baraja y que ningún índice
de un fold posterior aparece antes que uno de un fold anterior. También se
verifica que las features de lag/rolling de train no se contaminan con el bloque
de validación ni con folds futuros.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.sales_forecast.config import (
    FEATURE_COLUMNS,
    LEARNING_CURVE_TRAIN_SIZES,
    TARGET,
)
from scripts.sales_forecast.data import load_sales_data
from scripts.sales_forecast.features import build_features, training_frame
from scripts.sales_forecast.split import chronological_split
from scripts.sales_forecast.validation import (
    assert_fold_features_are_causal,
    build_learning_curve,
    build_time_series_folds,
    temporal_cross_validate,
)

DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "trackflow_sales.csv"
)


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    dataframe, _ = load_sales_data(DATA_PATH)
    return dataframe


@pytest.fixture(scope="module")
def featured(raw: pd.DataFrame) -> pd.DataFrame:
    return build_features(raw)


@pytest.fixture(scope="module")
def split(featured: pd.DataFrame):
    return chronological_split(featured)


@pytest.fixture(scope="module")
def train(featured: pd.DataFrame, split) -> pd.DataFrame:
    return training_frame(split.train).reset_index(drop=True)


def test_temporal_folds_preserve_chronological_order(train: pd.DataFrame) -> None:
    """Ningún fold mezcla train/validación ni invierte el orden temporal."""

    folds = build_time_series_folds(train)
    assert len(folds) >= 5

    for fold in folds:
        assert np.all(np.diff(fold.train_idx) > 0)
        assert np.all(np.diff(fold.validation_idx) > 0)
        assert np.intersect1d(fold.train_idx, fold.validation_idx).size == 0
        assert fold.train_idx.max() < fold.validation_idx.min()
        assert fold.train_end < fold.validation_start
        assert (
            fold.validation_start
            == fold.train_end + pd.DateOffset(months=1)
        )

    # Los bloques de validación son consecutivos y estrictamente crecientes.
    for previous, current in zip(folds, folds[1:]):
        assert previous.validation_idx.max() < current.validation_idx.min()
        assert previous.train_idx.max() < current.train_idx.max()
        assert set(previous.train_idx).issubset(set(current.train_idx))

    # La concatenación de todas las validaciones conserva el orden global:
    # ningún índice de un fold posterior aparece antes que uno de un anterior.
    all_validation_indices = np.concatenate(
        [fold.validation_idx for fold in folds]
    )
    assert np.all(np.diff(all_validation_indices) > 0)

    for earlier in folds:
        for later in folds:
            if later.fold_id <= earlier.fold_id:
                continue
            assert earlier.validation_idx.max() < later.validation_idx.min()
            assert set(earlier.validation_idx).isdisjoint(
                set(later.validation_idx)
            )


def test_temporal_cv_never_touches_holdout(
    train: pd.DataFrame, split
) -> None:
    """La CV solo puede usar meses del set de entrenamiento."""

    folds = build_time_series_folds(train)
    test_months = set(pd.to_datetime(split.test["month"]).tolist())
    cv_months = set(pd.to_datetime(train["month"]).tolist())

    assert cv_months.isdisjoint(test_months)
    assert max(cv_months) < min(test_months)
    assert max(cv_months) == pd.Timestamp("2023-12-01")

    for fold in folds:
        assert fold.validation_end <= pd.Timestamp("2023-12-01")
        assert fold.train_end <= pd.Timestamp("2023-12-01")


def test_fold_features_do_not_leak_from_validation_or_future(
    raw: pd.DataFrame, featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    """Truncar en las fronteras de cada fold no cambia las features."""

    folds = build_time_series_folds(train)
    for fold in folds:
        checks = assert_fold_features_are_causal(raw, featured, fold)
        assert checks["features_until_validation_end_match_full_series"] is True
        assert checks["training_features_match_truncation_at_train_end"] is True
        assert checks["validation_rows_use_only_past"] is True
        assert checks["validation_rows_checked_against_past"] == fold.n_validation


def test_first_validation_row_features_only_use_past(
    raw: pd.DataFrame, featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    """La fila del primer mes de validación se puede construir solo con t-1."""

    fold = build_time_series_folds(train)[0]
    month = fold.validation_start

    past = raw.loc[raw["month"] < month].copy()
    placeholder = {column: np.nan for column in past.columns}
    placeholder["month"] = month
    extended = pd.concat([past, pd.DataFrame([placeholder])], ignore_index=True)

    computed = build_features(extended)
    computed_row = computed.loc[
        computed["month"] == month, list(FEATURE_COLUMNS)
    ]
    full_row = featured.loc[
        featured["month"] == month, list(FEATURE_COLUMNS)
    ]

    np.testing.assert_allclose(
        computed_row.to_numpy(dtype=float),
        full_row.to_numpy(dtype=float),
        rtol=0,
        atol=0,
    )


def test_temporal_cv_summary_reports_mean_and_std(
    raw: pd.DataFrame, featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    """El resumen debe traer media ± desviación estándar por métrica."""

    result = temporal_cross_validate(
        train,
        featured=featured,
        raw_df=raw,
        n_estimators=40,
        verify_causality=False,
    )

    assert len(result["folds"]) >= 5
    assert result["summary"]["n_folds"] == len(result["folds"])
    assert result["cv"]["shuffle"] is False

    for mode in ("train", "validation"):
        for metric in ("mae_eur", "rmse_eur", "mape_pct"):
            summary = result["summary"][mode][metric]
            assert np.isfinite(summary["mean"])
            assert np.isfinite(summary["std"])
            assert summary["std"] >= 0
            assert summary["min"] <= summary["mean"] <= summary["max"]


def test_learning_curve_is_chronological_and_expanding(
    featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    """Cada punto entrena con historia anterior a la validación fija de 2023."""

    points = build_learning_curve(
        train,
        featured=featured,
        n_estimators=40,
    )

    assert [point["n_train_rows"] for point in points] == list(
        LEARNING_CURVE_TRAIN_SIZES
    )
    validation_windows = set()
    for point in points:
        assert point["train_end"] < point["validation_start"]
        validation_windows.add(
            (point["validation_start"], point["validation_end"])
        )
    assert validation_windows == {("2023-01", "2023-12")}

    sizes = [point["n_train_rows"] for point in points]
    assert sizes == sorted(sizes)


def test_temporal_cv_rejects_fewer_than_five_folds(train: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="al menos 5 folds"):
        build_time_series_folds(train, n_splits=4)


def test_learning_curve_rejects_size_larger_than_history(
    featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    with pytest.raises(ValueError, match="no cabe"):
        build_learning_curve(
            train,
            featured=featured,
            train_sizes=(24, 999),
            n_estimators=10,
        )


def test_fold_metrics_are_positive_and_finite(
    raw: pd.DataFrame, featured: pd.DataFrame, train: pd.DataFrame
) -> None:
    result = temporal_cross_validate(
        train,
        featured=featured,
        raw_df=raw,
        n_estimators=20,
        verify_causality=False,
    )
    for fold in result["folds"]:
        assert fold["train"]["mae_eur"] > 0
        assert fold["validation"]["mae_eur"] > 0
        assert fold["train"]["rmse_eur"] >= fold["train"]["mae_eur"]
        assert fold["validation"]["rmse_eur"] >= fold["validation"]["mae_eur"]
        assert np.isfinite(fold["validation"]["rmse_eur"])
        assert fold["n_train"] > 0
        assert fold["n_validation"] > 0

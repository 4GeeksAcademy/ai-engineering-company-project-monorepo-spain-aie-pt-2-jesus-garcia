"""Tests del pronóstico de ventas: split 8/2, causalidad y reproducibilidad.

El objetivo principal es demostrar que el corte de entrenamiento/test respeta
la regla de negocio (primeros 8 años / últimos 2) y que ninguna feature de una
fila mira al futuro, ni siquiera después de agrandar la serie o alterar los
meses de test.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.sales_forecast.config import (
    BASE_LAG_MONTHS,
    EXPECTED_COLUMNS,
    FEATURE_COLUMNS,
    GROWTH_TARGET_COLUMN,
    SEED,
    TARGET,
)
from scripts.sales_forecast.data import load_sales_data
from scripts.sales_forecast.features import (
    INTERNAL_LOG_COLUMN,
    build_features,
    recursive_feature_row,
)
from scripts.sales_forecast.metrics import (
    gini_accuracy_ratio,
    k2_score,
    population_stability_index,
)
from scripts.sales_forecast.model import (
    build_model,
    fit_forecaster,
    point_forecast,
)
from scripts.sales_forecast.split import (
    assert_no_leakage,
    chronological_split,
)

DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "trackflow_sales.csv"
)
TEST_START = pd.Timestamp("2024-01-01")


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


def test_raw_dataset_matches_company_context(raw: pd.DataFrame) -> None:
    """El CSV debe ser exactamente el contrato descrito en CONTEXT/spec."""

    csv_columns = pd.read_csv(DATA_PATH, nrows=0).columns.tolist()
    assert csv_columns == list(EXPECTED_COLUMNS)
    assert list(raw.columns) == [
        column for column in EXPECTED_COLUMNS if column != "market"
    ]
    assert len(raw) == 120
    assert raw["month"].min() == pd.Timestamp("2016-01-01")
    assert raw["month"].max() == pd.Timestamp("2025-12-01")
    assert raw["month"].is_monotonic_increasing
    assert not raw["month"].duplicated().any()
    assert raw.isna().sum().sum() == 0
    assert (raw[TARGET] > 0).all()

    months_by_year = raw.groupby(raw["month"].dt.year).size()
    assert set(months_by_year.index) == set(range(2016, 2026))
    assert (months_by_year == 12).all()


def test_split_uses_first_8_and_last_2_years(split) -> None:
    """Entrenamiento = 96 primeros meses; test = 24 últimos."""

    assert len(split.train) == 8 * 12
    assert len(split.test) == 2 * 12
    assert split.train["month"].min() == pd.Timestamp("2016-01-01")
    assert split.train["month"].max() == pd.Timestamp("2023-12-01")
    assert split.test["month"].min() == TEST_START
    assert split.test["month"].max() == pd.Timestamp("2025-12-01")


def test_split_has_no_overlap_or_data_leakage(split) -> None:
    """Ningún mes/año se comparte y el corte es estrictamente cronológico."""

    train_months = set(pd.to_datetime(split.train["month"]))
    test_months = set(pd.to_datetime(split.test["month"]))

    assert train_months.isdisjoint(test_months)
    assert max(train_months) < min(test_months)
    assert {month.year for month in train_months}.isdisjoint(
        {month.year for month in test_months}
    )

    # La guarda del propio pipeline debe aceptar el split y rechazar el solape.
    assert_no_leakage(split.train, split.test)

    with pytest.raises(ValueError, match="Fuga de datos"):
        assert_no_leakage(split.train, pd.concat([split.train.tail(1), split.test]))


def test_split_rejects_series_without_10_full_years(featured: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="Se esperaban 120 meses"):
        chronological_split(featured.iloc[:112])


def test_features_are_causal_when_future_rows_are_removed(
    raw: pd.DataFrame,
) -> None:
    """Calcular features con la serie completa o truncada da lo mismo en train."""

    full = build_features(raw)
    truncated = build_features(raw.loc[raw["month"] < TEST_START].reset_index(drop=True))

    columns = [*FEATURE_COLUMNS, INTERNAL_LOG_COLUMN, GROWTH_TARGET_COLUMN, TARGET]
    merged = truncated.merge(full, on="month", suffixes=("_trunc", "_full"))
    assert len(merged) == 96

    for column in columns:
        np.testing.assert_allclose(
            merged[f"{column}_trunc"].to_numpy(dtype=float),
            merged[f"{column}_full"].to_numpy(dtype=float),
            rtol=0,
            atol=0,
            err_msg=f"La feature '{column}' cambió al truncar el futuro",
        )


def test_perturbing_future_values_does_not_change_training_features(
    raw: pd.DataFrame,
) -> None:
    """Si el futuro cambia, las features de los meses pasados deben ser idénticas."""

    original = build_features(raw)

    perturbed_raw = raw.copy()
    future_mask = perturbed_raw["month"] >= TEST_START
    perturbed_raw.loc[future_mask, TARGET] = (
        perturbed_raw.loc[future_mask, TARGET] * 3.0
    )
    perturbed_raw.loc[future_mask, "shipments_processed"] = (
        perturbed_raw.loc[future_mask, "shipments_processed"] * 4
    )
    perturbed = build_features(perturbed_raw)

    past = original["month"] < TEST_START
    for column in FEATURE_COLUMNS:
        np.testing.assert_allclose(
            original.loc[past, column].to_numpy(dtype=float),
            perturbed.loc[past, column].to_numpy(dtype=float),
            rtol=0,
            atol=0,
            err_msg=f"'{column}' en train se contaminó con valores futuros",
        )


def test_target_and_log_revenue_are_not_features() -> None:
    assert TARGET not in FEATURE_COLUMNS
    assert INTERNAL_LOG_COLUMN not in FEATURE_COLUMNS
    assert GROWTH_TARGET_COLUMN not in FEATURE_COLUMNS


def test_recursive_feature_row_matches_batch_features(
    featured: pd.DataFrame,
) -> None:
    """La fila recursiva de un mes debe coincidir con la construida en batch."""

    start = 96
    growth_history = featured.loc[
        : start - 1, GROWTH_TARGET_COLUMN
    ].to_numpy(dtype=float).tolist()
    row = recursive_feature_row(
        month=int(featured.loc[start, "month"].month),
        growth_history=growth_history,
    )

    batch = featured.loc[start]
    for column in FEATURE_COLUMNS:
        assert row[column] == pytest.approx(float(batch[column]), rel=1e-12)


def test_test_split_has_complete_features(
    split, featured: pd.DataFrame
) -> None:
    test_features = featured.loc[featured["month"] >= TEST_START]
    assert len(test_features) == 24
    assert not test_features[list(FEATURE_COLUMNS)].isna().any().any()


def test_training_is_reproducible_with_fixed_seed(
    split, featured: pd.DataFrame
) -> None:
    """Dos entrenamientos con random_state=42 dan predicciones idénticas."""

    train = split.train.dropna(
        subset=[*FEATURE_COLUMNS, GROWTH_TARGET_COLUMN]
    )
    test = split.test
    base_revenue = (
        featured[TARGET].shift(BASE_LAG_MONTHS).iloc[len(split.train) :].to_numpy()
    )
    predictions = []

    for _ in range(2):
        model = build_model(n_estimators=40, random_state=SEED, n_jobs=1)
        fit_forecaster(model, train, train[GROWTH_TARGET_COLUMN])
        predictions.append(point_forecast(model, test, base_revenue))

    np.testing.assert_array_equal(predictions[0], predictions[1])


def test_metrics_sanity_checks() -> None:
    stable = np.linspace(100, 200, 30)
    shifted = stable * 1.01
    assert population_stability_index(stable, stable)["psi"] == pytest.approx(
        0.0, abs=1e-9
    )
    assert population_stability_index(stable, shifted)["psi"] < 0.1

    values = np.arange(1, 25, dtype=float)
    assert gini_accuracy_ratio(values, values) == pytest.approx(1.0)
    assert gini_accuracy_ratio(values, values[::-1]) == pytest.approx(-1.0)

    perfect = k2_score(values, values)
    assert perfect["k2_normalized"] == pytest.approx(1.0)
    # El K2 mide asociación/concentración, no acierto: una predicción aleatoria
    # debe puntuar menos que la ordenación perfecta.
    shuffled = np.random.default_rng(SEED).permutation(values)
    assert perfect["k2_normalized"] > k2_score(values, shuffled)["k2_normalized"]

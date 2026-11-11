"""Split cronológico 8 años / 2 años con guardas anti-leakage.

El dataset es una serie temporal mensual, así que el split nunca es aleatorio:
entrenar con meses futuros y evaluar con pasados inflaría las métricas y
rompería la causalidad del pronóstico. El corte se hace por número de filas
(8 × 12 = 96 y 2 × 12 = 24) y se valida que coincida con años naturales
completos, sin meses compartidos ni huecos entre ambos conjuntos.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import MONTHS_PER_YEAR, TEST_YEARS, TRAIN_YEARS


@dataclass(frozen=True)
class DataSplit:
    """Resultado del split, con metadatos listos para el informe de métricas."""

    train: pd.DataFrame
    test: pd.DataFrame
    train_years: int
    test_years: int

    @property
    def train_months(self) -> int:
        return len(self.train)

    @property
    def test_months(self) -> int:
        return len(self.test)

    def summary(self) -> dict[str, object]:
        return {
            "train_rows": self.train_months,
            "test_rows": self.test_months,
            "train_years": self.train_years,
            "test_years": self.test_years,
            "train_start": self.train["month"].min().strftime("%Y-%m"),
            "train_end": self.train["month"].max().strftime("%Y-%m"),
            "test_start": self.test["month"].min().strftime("%Y-%m"),
            "test_end": self.test["month"].max().strftime("%Y-%m"),
        }


def chronological_split(
    df: pd.DataFrame,
    *,
    train_years: int = TRAIN_YEARS,
    test_years: int = TEST_YEARS,
    months_per_year: int = MONTHS_PER_YEAR,
) -> DataSplit:
    """Divide la serie en los primeros ``train_years`` y los últimos ``test_years``."""

    if "month" not in df.columns:
        raise ValueError("El DataFrame debe tener una columna 'month'")
    if df.empty:
        raise ValueError("El dataset está vacío")

    ordered = df.sort_values("month").reset_index(drop=True)
    _validate_monthly_continuity(ordered)

    expected_train = train_years * months_per_year
    expected_test = test_years * months_per_year
    expected_total = expected_train + expected_test
    if len(ordered) != expected_total:
        raise ValueError(
            f"Se esperaban {expected_total} meses ({train_years} años de train + "
            f"{test_years} de test) y hay {len(ordered)}. El split 8/2 requiere "
            "una serie mensual completa de 10 años."
        )

    train = ordered.iloc[:expected_train].reset_index(drop=True)
    test = ordered.iloc[expected_train:].reset_index(drop=True)

    assert_no_leakage(train, test)

    if train["month"].min().month != 1 or train["month"].max().month != 12:
        raise ValueError(
            "El bloque de entrenamiento no cubre años naturales completos "
            f"({train['month'].min():%Y-%m} → {train['month'].max():%Y-%m})"
        )
    if test["month"].min().month != 1 or test["month"].max().month != 12:
        raise ValueError(
            "El bloque de test no cubre años naturales completos "
            f"({test['month'].min():%Y-%m} → {test['month'].max():%Y-%m})"
        )

    return DataSplit(
        train=train,
        test=test,
        train_years=train_years,
        test_years=test_years,
    )


def assert_no_leakage(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Falla si train y test comparten meses o el orden temporal se rompe."""

    if train.empty or test.empty:
        raise ValueError("Train y test deben tener filas")

    train_months = set(pd.to_datetime(train["month"]))
    test_months = set(pd.to_datetime(test["month"]))

    overlap = train_months.intersection(test_months)
    if overlap:
        sample = sorted(month.strftime("%Y-%m") for month in overlap)[:5]
        raise ValueError(f"Fuga de datos: meses presentes en train y test: {sample}")

    train_end = pd.to_datetime(train["month"]).max()
    test_start = pd.to_datetime(test["month"]).min()
    if train_end >= test_start:
        raise ValueError(
            "Fuga de datos: el último mes de train "
            f"({train_end:%Y-%m}) no es anterior al primero de test "
            f"({test_start:%Y-%m})"
        )

    expected_test_start = train_end + pd.DateOffset(months=1)
    if test_start != expected_test_start:
        raise ValueError(
            "Hay un hueco entre train y test: se esperaba "
            f"{expected_test_start:%Y-%m} y empieza en {test_start:%Y-%m}"
        )

    train_years = set(pd.to_datetime(train["month"]).dt.year)
    test_years = set(pd.to_datetime(test["month"]).dt.year)
    if train_years.intersection(test_years):
        raise ValueError(
            f"Fuga de datos: años compartidos entre train y test: "
            f"{sorted(train_years.intersection(test_years))}"
        )


def _validate_monthly_continuity(df: pd.DataFrame) -> None:
    """Comprueba que la serie tiene exactamente un registro por mes."""

    months = pd.to_datetime(df["month"])
    if months.duplicated().any():
        raise ValueError("Hay meses duplicados en el dataset")
    if not months.is_monotonic_increasing:
        raise ValueError("Los meses no están ordenados")
    expected = pd.date_range(months.min(), months.max(), freq="MS")
    if len(expected) != len(months):
        raise ValueError(
            "La serie mensual tiene huecos: "
            f"{len(months)} filas para {len(expected)} meses esperados"
        )

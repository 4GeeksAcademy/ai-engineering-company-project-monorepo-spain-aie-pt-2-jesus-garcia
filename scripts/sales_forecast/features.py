"""Construcción de features causales para el pronóstico de ingresos.

El modelo no aprende el nivel de ingresos directamente: aprende el
**crecimiento interanual logarítmico**

    yoy_log_growth(t) = log(revenue_t) - log(revenue_{t-12})

que es una serie estacionaria. Así el Random Forest no tiene que extrapolar
niveles fuera del rango de entrenamiento (los árboles no extrapolan) y el
pronóstico final se reconstruye multiplicando por el ingreso del mismo mes del
año anterior, conocido en el momento de predecir.

Regla de oro: la fila del mes ``t`` solo puede usar información disponible
antes de que empiece ``t``. Por eso todas las transformaciones de la serie usan
``shift`` positivo o ventanas que terminan en ``t-1``. El calendario del mes
objetivo (``month_sin``, ``month_cos``, noviembre/diciembre, febrero) sí se
conoce de antemano.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BASE_LAG_MONTHS, FEATURE_COLUMNS, GROWTH_TARGET_COLUMN, TARGET

INTERNAL_LOG_COLUMN = "log_revenue"
_YOY_LAG = BASE_LAG_MONTHS


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Añade features causales, ``log_revenue`` y el target de crecimiento."""

    required = {"month", TARGET}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas para construir features: {sorted(missing)}")

    out = df.copy().reset_index(drop=True)
    if not out["month"].is_monotonic_increasing:
        raise ValueError("Las filas deben estar ordenadas por 'month'")

    log_revenue = np.log(out[TARGET].astype(float))
    out[INTERNAL_LOG_COLUMN] = log_revenue

    # Target estacionario: crecimiento interanual logarítmico.
    growth = log_revenue - log_revenue.shift(_YOY_LAG)
    out[GROWTH_TARGET_COLUMN] = growth

    month = out["month"].dt.month
    out["month_sin"] = np.sin(2 * np.pi * month / 12)
    out["month_cos"] = np.cos(2 * np.pi * month / 12)
    out["is_peak_season"] = month.isin([11, 12]).astype(int)
    out["is_february_dip"] = (month == 2).astype(int)

    # Lags del crecimiento: valores de t-1, t-2, t-3 y del mismo mes del año
    # anterior. Todos son pasados estrictos.
    out["yoy_growth_lag_1"] = growth.shift(1)
    out["yoy_growth_lag_2"] = growth.shift(2)
    out["yoy_growth_lag_3"] = growth.shift(3)
    out["yoy_growth_lag_12"] = growth.shift(12)

    # Medias rodantes del crecimiento reciente (shift(1) para excluir t).
    for window in (3, 6):
        out[f"yoy_rolling_mean_{window}"] = (
            growth.shift(1).rolling(window=window, min_periods=window).mean()
        )

    return out


def recursive_feature_row(
    *,
    month: int,
    growth_history: list[float] | np.ndarray,
    require_history: int = _YOY_LAG,
) -> dict[str, float]:
    """Construye la fila de features para un mes futuro sin mirar actuales.

    ``growth_history`` contiene únicamente los crecimientos conocidos hasta el
    mes anterior (actuales antes del corte y predicciones después). Se usa en
    el backtest recursivo, donde las predicciones se realimentan como si
    fueran historia.
    """

    history = np.asarray(growth_history, dtype=float)
    if history.size < require_history:
        raise ValueError(
            f"Se necesitan al menos {require_history} meses de historia; "
            f"hay {history.size}"
        )
    if not 1 <= month <= 12:
        raise ValueError(f"Mes inválido: {month}")

    return {
        "month_sin": float(np.sin(2 * np.pi * month / 12)),
        "month_cos": float(np.cos(2 * np.pi * month / 12)),
        "is_peak_season": float(month in (11, 12)),
        "is_february_dip": float(month == 2),
        "yoy_growth_lag_1": float(history[-1]),
        "yoy_growth_lag_2": float(history[-2]),
        "yoy_growth_lag_3": float(history[-3]),
        "yoy_growth_lag_12": float(history[-12]),
        "yoy_rolling_mean_3": float(history[-3:].mean()),
        "yoy_rolling_mean_6": float(history[-6:].mean()),
    }


def training_frame(featured: pd.DataFrame) -> pd.DataFrame:
    """Filas con features y target completos (descarta los primeros 2 años)."""

    required = [*FEATURE_COLUMNS, GROWTH_TARGET_COLUMN]
    return featured.dropna(subset=required).reset_index(drop=True)

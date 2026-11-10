"""Entrenamiento, predicción puntual, banda de variabilidad y backtest recursivo.

El bosque aprende el crecimiento interanual logarítmico (serie estacionaria).
La conversión a euros multiplica ``exp(crecimiento_predicho)`` por el ingreso
del mismo mes del año anterior. En one-step esa base es un dato real conocido;
en el backtest recursivo, cuando el horizonte supera 12 meses, la base pasa a
ser una predicción previa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import (
    BASE_LAG_MONTHS,
    FEATURE_COLUMNS,
    GROWTH_TARGET_COLUMN,
    INTERVAL_QUANTILES,
    MAX_FEATURES,
    MIN_SAMPLES_LEAF,
    N_ESTIMATORS,
    N_JOBS,
    SEED,
    TARGET,
)
from .features import recursive_feature_row


def build_model(
    *,
    n_estimators: int = N_ESTIMATORS,
    random_state: int = SEED,
    min_samples_leaf: int = MIN_SAMPLES_LEAF,
    max_features: float = MAX_FEATURES,
    n_jobs: int = N_JOBS,
) -> Pipeline:
    """Random Forest con escalado previo y semilla fija.

    El ``StandardScaler`` no cambia las predicciones de un bosque (es invariante
    a transformaciones monótonas), pero deja el pipeline preparado para
    comparar con modelos lineales y cumple el requisito de escalar magnitudes
    distintas (senos/cosenos frente a crecimientos logarítmicos).
    """

    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=n_estimators,
                    min_samples_leaf=min_samples_leaf,
                    max_features=max_features,
                    random_state=random_state,
                    n_jobs=n_jobs,
                    bootstrap=True,
                ),
            ),
        ]
    )


def fit_forecaster(
    model: Pipeline,
    features: pd.DataFrame,
    growth_target: pd.Series | np.ndarray,
) -> Pipeline:
    """Ajusta el modelo sobre el crecimiento interanual logarítmico."""

    target = np.asarray(growth_target, dtype=float)
    if not np.isfinite(target).all():
        raise ValueError("El target de crecimiento contiene NaN o infinitos")
    return model.fit(features[list(FEATURE_COLUMNS)], target)


def point_forecast(
    model: Pipeline,
    features: pd.DataFrame,
    base_revenue: np.ndarray | pd.Series,
) -> np.ndarray:
    """Convierte el crecimiento predicho en ingresos EUR usando la base t-12."""

    growth = model.predict(features[list(FEATURE_COLUMNS)])
    base = np.asarray(base_revenue, dtype=float)
    if base.shape != growth.shape:
        raise ValueError(
            f"base_revenue tiene forma {base.shape} y la predicción {growth.shape}"
        )
    if (base <= 0).any():
        raise ValueError("La base de ingresos debe ser positiva")
    return np.exp(growth) * base


def forecast_interval(
    model: Pipeline,
    features: pd.DataFrame,
    base_revenue: np.ndarray | pd.Series,
    *,
    quantiles: tuple[float, ...] = INTERVAL_QUANTILES,
) -> dict[str, np.ndarray]:
    """Banda empírica a partir de la dispersión entre árboles del bosque.

    No es un intervalo de confianza calibrado: refleja cuánto discrepan los
    árboles del ensamble para ese mes. Es útil para comunicar variabilidad
    relativa, no para garantizar cobertura frecuentista.
    """

    scaler = model.named_steps["scaler"]
    regressor = model.named_steps["regressor"]
    scaled = scaler.transform(features[list(FEATURE_COLUMNS)])
    base = np.asarray(base_revenue, dtype=float)

    per_tree_growth = np.vstack(
        [tree.predict(scaled) for tree in regressor.estimators_]
    )
    per_tree_revenue = np.exp(per_tree_growth) * base[np.newaxis, :]

    result = {"mean": per_tree_revenue.mean(axis=0)}
    for quantile in quantiles:
        result[f"q{int(round(quantile * 100)):02d}"] = np.quantile(
            per_tree_revenue, quantile, axis=0
        )
    return result


def recursive_forecast(
    model: Pipeline,
    featured: pd.DataFrame,
    *,
    start_index: int,
    horizon: int,
) -> np.ndarray:
    """Pronóstico multi-paso realimentando las propias predicciones.

    En cada paso la fila de features se construye solo con la historia
    disponible hasta el mes anterior (actuales antes del corte y predicciones
    después). La base de ingresos es el valor de hace 12 meses: real para los
    primeros 12 pasos y predicho a partir de ahí.
    """

    if start_index < BASE_LAG_MONTHS or start_index + horizon > len(featured):
        raise ValueError(
            f"Ventana recursiva inválida: start={start_index}, horizon={horizon}, "
            f"filas={len(featured)}"
        )

    growth_history = list(
        featured.loc[: start_index - 1, GROWTH_TARGET_COLUMN].to_numpy(dtype=float)
    )
    revenue_history = list(
        featured.loc[: start_index - 1, TARGET].to_numpy(dtype=float)
    )
    predictions: list[float] = []

    for step in range(horizon):
        row_index = start_index + step
        month = int(featured.loc[row_index, "month"].month)
        row = recursive_feature_row(month=month, growth_history=growth_history)
        features = pd.DataFrame([row], columns=list(FEATURE_COLUMNS))
        growth_prediction = float(model.predict(features)[0])
        base_revenue = revenue_history[row_index - BASE_LAG_MONTHS]
        prediction = float(np.exp(growth_prediction) * base_revenue)
        predictions.append(prediction)
        revenue_history.append(prediction)
        growth_history.append(growth_prediction)

    return np.asarray(predictions, dtype=float)


def feature_importances(model: Pipeline) -> dict[str, float]:
    """Importancia de cada feature según el bosque, ordenada de mayor a menor."""

    regressor = model.named_steps["regressor"]
    values = regressor.feature_importances_
    ranking = sorted(
        zip(FEATURE_COLUMNS, values, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    return {name: float(value) for name, value in ranking}


__all__ = [
    "build_model",
    "feature_importances",
    "fit_forecaster",
    "forecast_interval",
    "point_forecast",
    "recursive_forecast",
]

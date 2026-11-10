"""Métricas de evaluación sobre el conjunto de test.

Incluye las cuatro métricas exigidas por el briefing:

* ``MSE`` (y RMSE/MAE/MAPE como apoyo) — error de magnitud.
* ``PSI`` — estabilidad de la distribución entre train y test.
* ``Gini`` — capacidad de ordenar meses buenos y malos (accuracy ratio).
* ``K2`` — score bayesiano de asociación entre el bin real y el predicho.

Ninguna se calcula sobre entrenamiento: todas reciben las predicciones del
bloque de test.
"""

from __future__ import annotations

from math import lgamma

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score

from .config import K2_BINS, PSI_BINS, PSI_MODERATE_THRESHOLD, PSI_STABLE_THRESHOLD

_EPSILON = 1e-6


def regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    reference_mean: float,
) -> dict[str, float]:
    """MSE, RMSE, MAE y MAPE, con el MSE relativizado al ingreso medio."""

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mse = float(mean_squared_error(y_true, y_pred))
    rmse = float(np.sqrt(mse))
    mae = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {
        "mse": mse,
        "rmse": rmse,
        "mae": mae,
        "mape_pct": mape,
        "mse_pct_of_train_mean_revenue": float(
            mse / (reference_mean**2) * 100
        ),
        "rmse_pct_of_train_mean_revenue": float(rmse / reference_mean * 100),
        "train_mean_revenue_eur": float(reference_mean),
    }


def population_stability_index(
    reference: np.ndarray,
    comparison: np.ndarray,
    *,
    n_bins: int = PSI_BINS,
) -> dict[str, object]:
    """PSI entre la distribución de referencia (train) y la de test.

    ``PSI = Σ (p_test − p_train) · ln(p_test / p_train)`` usando bins por
    cuantiles del train. Umbrales habituales: <0.10 estable, 0.10–0.25 cambio
    moderado, >0.25 cambio significativo.
    """

    reference = np.asarray(reference, dtype=float)
    comparison = np.asarray(comparison, dtype=float)
    if reference.size == 0 or comparison.size == 0:
        raise ValueError("PSI necesita muestras no vacías en train y test")

    edges = _quantile_edges(reference, n_bins)
    reference_counts, _ = np.histogram(reference, bins=edges)
    comparison_counts, _ = np.histogram(comparison, bins=edges)

    reference_share = np.clip(reference_counts / reference_counts.sum(), _EPSILON, None)
    comparison_share = np.clip(
        comparison_counts / comparison_counts.sum(), _EPSILON, None
    )
    contributions = (comparison_share - reference_share) * np.log(
        comparison_share / reference_share
    )
    value = float(np.sum(contributions))
    return {
        "psi": value,
        "interpretation": psi_interpretation(value),
        "bins": int(len(edges) - 1),
    }


def psi_interpretation(value: float) -> str:
    """Etiqueta cualitativa del PSI según los umbrales de la industria."""

    if value < PSI_STABLE_THRESHOLD:
        return "estable"
    if value < PSI_MODERATE_THRESHOLD:
        return "cambio moderado"
    return "cambio significativo"


def gini_accuracy_ratio(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Gini = 2·AUC − 1 sobre meses por encima/debajo de la mediana del test.

    Un Gini cercano a 1 significa que el modelo ordena bien qué meses serán
    fuertes (nov/dic) y cuáles débiles (feb), aunque su nivel absoluto no sea
    perfecto. Un Gini 0 equivale a ordenar al azar.
    """

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    labels = (y_true > np.median(y_true)).astype(int)
    if np.unique(labels).size < 2:
        raise ValueError("El Gini necesita al menos dos clases en el test")

    return float(2 * roc_auc_score(labels, y_pred) - 1)


def k2_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    n_bins: int = K2_BINS,
) -> dict[str, float]:
    """Score K2 (Bayesiano-Dirichlet) sobre bin(real) × bin(predicho).

    Se discretizan el ingreso real y el predicho con los mismos cortes
    (cuantiles del real) y se calcula el score K2 tratando el bin predicho como
    padre y el real como hijo. Premia que la predicción concentre el bin real
    correcto. Se reporta el valor crudo (más cercano a 0 = mejor), por muestra,
    y una versión normalizada 0–1 frente a una tabla de independencia y una
    referencia diagonal.
    """

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    edges = _finite_edges(y_true, n_bins)
    true_bins = np.digitize(y_true, edges[1:-1])
    pred_bins = np.digitize(y_pred, edges[1:-1])
    effective_bins = len(edges) - 1

    table = np.zeros((effective_bins, effective_bins), dtype=float)
    for true_bin, pred_bin in zip(true_bins, pred_bins, strict=True):
        table[int(pred_bin), int(true_bin)] += 1

    score = _k2_from_table(table)
    parent_counts = table.sum(axis=1)
    child_counts = table.sum(axis=0)
    total = table.sum()

    # Referencia de independencia: predicción sin información sobre el real.
    independent = np.outer(parent_counts, child_counts) / total
    independent_score = _k2_from_table(independent)

    # Referencia diagonal: cada predicción cae en el bin real con la misma
    # marginal que el modelo (no es necesariamente el máximo teórico del K2,
    # pero sí una cota superior razonable para normalizar).
    diagonal = np.diag(parent_counts)
    diagonal_score = _k2_from_table(diagonal)

    denominator = diagonal_score - independent_score
    normalized = (
        float(np.clip((score - independent_score) / denominator, 0.0, 1.0))
        if abs(denominator) > _EPSILON
        else 0.0
    )

    return {
        "k2": score,
        "k2_per_sample": score / float(total),
        "k2_normalized": normalized,
        "bins": int(effective_bins),
        "samples": int(total),
    }


def _k2_from_table(table: np.ndarray) -> float:
    """Fórmula K2 para una tabla de contingencia padre(fila) × hijo(columna)."""

    n_children = table.shape[1]
    score = 0.0
    for row in range(table.shape[0]):
        parent_total = float(table[row].sum())
        if parent_total <= 0:
            continue
        score += lgamma(n_children) - lgamma(parent_total + n_children)
        for count in table[row]:
            # lgamma(0 + 1) = 0, así que solo suman las celdas no vacías.
            score += lgamma(float(count) + 1)
    return float(score)


def _quantile_edges(reference: np.ndarray, n_bins: int) -> np.ndarray:
    """Cortes por cuantiles con extremos abiertos para no perder valores."""

    edges = _finite_edges(reference, n_bins)
    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges


def _finite_edges(reference: np.ndarray, n_bins: int) -> np.ndarray:
    """Cortes únicos por cuantiles; cae a cortes lineales si hay pocos valores."""

    if n_bins < 2:
        raise ValueError("Se necesitan al menos 2 bins")
    quantiles = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.unique(np.quantile(reference, quantiles))
    if edges.size < 3:
        minimum = float(reference.min())
        maximum = float(reference.max())
        if maximum <= minimum:
            raise ValueError("La serie de referencia es constante; PSI/K2 no aplica")
        edges = np.linspace(minimum, maximum, n_bins + 1)
    return edges.astype(float)

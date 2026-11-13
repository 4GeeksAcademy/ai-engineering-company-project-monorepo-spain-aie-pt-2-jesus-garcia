"""Visualización del pronóstico frente a los datos reales de test.

Genera una figura de dos paneles:

1. Serie real (contexto de train + 24 meses de test) con la predicción puntual
   y el área de variabilidad p10–p90 (y p5–p95) de las predicciones de los
   árboles del bosque.
2. Error relativo mes a mes para ver dónde se concentra la desviación.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from .config import SEED


def plot_forecast(
    *,
    context: pd.DataFrame,
    test_predictions: pd.DataFrame,
    metrics: dict[str, object],
    output_path: str | Path,
    title: str = "TrackFlow · Pronóstico de ingresos mensuales",
) -> Path:
    """Guarda la figura comparando real, predicción y banda de variabilidad."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_series, ax_error) = plt.subplots(
        2,
        1,
        figsize=(14, 9),
        gridspec_kw={"height_ratios": [2.2, 1.0]},
    )

    # Matplotlib 3.11 no convierte de forma fiable ``datetime64[us]`` de pandas
    # 3; se normaliza a ``datetime.datetime`` de Python.
    context_months = pd.to_datetime(context["month"]).dt.to_pydatetime()
    test_months = pd.to_datetime(test_predictions["month"]).dt.to_pydatetime()

    # --- Panel 1: serie con banda de variabilidad -------------------------
    ax_series.plot(
        context_months,
        context["revenue_eur"],
        color="#9CA3AF",
        linewidth=1.8,
        label="Real (contexto de entrenamiento)",
    )
    ax_series.plot(
        test_months,
        test_predictions["revenue_eur"],
        color="#111827",
        linewidth=2.4,
        marker="o",
        markersize=4,
        label="Real (test 2024–2025)",
    )
    ax_series.plot(
        test_months,
        test_predictions["prediction_eur"],
        color="#2563EB",
        linewidth=2.4,
        marker="o",
        markersize=4,
        label="Predicción Random Forest",
    )
    if {"lower_outer_eur", "upper_outer_eur"}.issubset(test_predictions.columns):
        ax_series.fill_between(
            test_months,
            test_predictions["lower_outer_eur"],
            test_predictions["upper_outer_eur"],
            color="#93C5FD",
            alpha=0.35,
            label="Banda p5–p95",
        )
    ax_series.fill_between(
        test_months,
        test_predictions["lower_eur"],
        test_predictions["upper_eur"],
        color="#3B82F6",
        alpha=0.30,
        label="Banda p10–p90",
    )
    if "recursive_prediction_eur" in test_predictions.columns:
        ax_series.plot(
            test_months,
            test_predictions["recursive_prediction_eur"],
            color="#F59E0B",
            linewidth=1.8,
            linestyle="--",
            label="Predicción recursiva 24 pasos",
        )

    boundary = test_months[0]
    ax_series.axvline(
        boundary,
        color="#6B7280",
        linestyle=":",
        linewidth=1.4,
        label="Corte train / test",
    )

    ax_series.set_title(title, fontsize=15, fontweight="bold", loc="left")
    ax_series.set_ylabel("Ingresos mensuales (EUR)")
    ax_series.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value / 1_000_000:.2f} M€")
    )
    ax_series.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax_series.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_series.grid(axis="y", alpha=0.25, linestyle="--")
    ax_series.legend(loc="upper left", fontsize=9, frameon=True)

    one_step = metrics.get("one_step", {})
    kpi_text = (
        f"MSE = {one_step.get('mse', float('nan')):,.0f} €²"
        f"   ·   RMSE = {one_step.get('rmse', float('nan')):,.0f} €"
        f"   ·   MAPE = {one_step.get('mape_pct', float('nan')):.2f}%\n"
        f"PSI = {one_step.get('psi_revenue', {}).get('psi', float('nan')):.3f}"
        f"   ·   Gini = {one_step.get('gini', float('nan')):.3f}"
        f"   ·   K2 = {one_step.get('k2', {}).get('k2', float('nan')):.2f}"
    )
    ax_series.text(
        0.01,
        0.03,
        kpi_text,
        transform=ax_series.transAxes,
        fontsize=9,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.85},
    )

    # --- Panel 2: error relativo ---------------------------------------
    residual_pct = (
        (test_predictions["revenue_eur"] - test_predictions["prediction_eur"])
        / test_predictions["revenue_eur"]
        * 100
    )
    colors = ["#DC2626" if value < 0 else "#059669" for value in residual_pct]
    ax_error.bar(
        test_months,
        residual_pct,
        width=20,
        color=colors,
        alpha=0.85,
    )
    ax_error.axhline(0, color="#111827", linewidth=1.0)
    ax_error.set_ylabel("Error relativo (%)")
    ax_error.set_xlabel("Mes")
    ax_error.set_title(
        "Desviación mensual (real − predicción) / real", fontsize=11, loc="left"
    )
    ax_error.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax_error.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_error.grid(axis="y", alpha=0.25, linestyle="--")

    fig.text(
        0.99,
        0.01,
        f"Random Forest · random_state={SEED} · banda = dispersión entre árboles",
        ha="right",
        fontsize=8,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path

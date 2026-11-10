"""Pipeline reproducible de pronóstico de ventas mensuales de TrackFlow.

Ver ``docs/models-training-rag/README.md`` para la decisión de algoritmo, las
métricas y la interpretación de los resultados.
"""

from __future__ import annotations

__all__ = ["run_forecast_pipeline"]


def run_forecast_pipeline(*args, **kwargs):
    """Import perezoso para no cargar sklearn/matplotlib al importar el paquete."""

    from .pipeline import run_forecast_pipeline as _run

    return _run(*args, **kwargs)

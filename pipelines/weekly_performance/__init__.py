"""Pipeline semanal de desempeño por almacén y cliente.

La lógica pura vive en :mod:`core`; ``tasks`` y ``flow`` son la capa de
orquestación con Prefect. ``core`` no importa Prefect para que los tests
unitarios sean rápidos y no dependan de un servidor.
"""

from .core import (  # noqa: F401
    QualityReport,
    WeekResult,
    aggregate_kpis,
    evaluate_quality,
    extract_week,
    normalize_validate,
    resolve_target_weeks,
    run_week,
)

__all__ = [
    "QualityReport",
    "WeekResult",
    "aggregate_kpis",
    "evaluate_quality",
    "extract_week",
    "normalize_validate",
    "resolve_target_weeks",
    "run_week",
]

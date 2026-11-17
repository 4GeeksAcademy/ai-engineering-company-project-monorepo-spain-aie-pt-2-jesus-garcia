"""Registro de generadores por departamento.

Cada departamento tiene su propio agente generador en un módulo separado. Este
registro es la única forma de obtener uno: si el handoff pide un departamento
fuera del catálogo, falla en vez de improvisar.
"""

from __future__ import annotations

from .base import DepartmentGenerator, GeneratorError
from .lastmile import GENERATOR as LASTMILE_GENERATOR
from .reverse import GENERATOR as REVERSE_GENERATOR
from .warehouse import GENERATOR as WAREHOUSE_GENERATOR

GENERATORS: dict[str, DepartmentGenerator] = {
    generator.department_id: generator
    for generator in (
        WAREHOUSE_GENERATOR,
        LASTMILE_GENERATOR,
        REVERSE_GENERATOR,
    )
}


def generator_for(department_id: str) -> DepartmentGenerator:
    try:
        return GENERATORS[department_id]
    except KeyError as exc:
        raise GeneratorError(
            f"No existe generador para el departamento {department_id!r}."
        ) from exc


__all__ = [
    "GENERATORS",
    "DepartmentGenerator",
    "GeneratorError",
    "generator_for",
]

"""Recepción de RFPs de TrackFlow (Hito 9, Parte 1).

Punto de entrada del pipeline dedicado ``rfp_intake``. La API encola
``run_rfp_intake`` y este paquete se encarga de convertir el PDF a Markdown,
clasificarlo, extraer metadatos, orquestar workers por departamento y sintetizar
el handoff para Ventas.
"""

from .catalog import DEPARTMENTS, DEPARTMENT_ORDER, SERVICES
from .graph import build_rfp_graph
from .runner import RfpPipelineError, run_rfp_intake

__all__ = [
    "DEPARTMENTS",
    "DEPARTMENT_ORDER",
    "SERVICES",
    "RfpPipelineError",
    "build_rfp_graph",
    "run_rfp_intake",
]

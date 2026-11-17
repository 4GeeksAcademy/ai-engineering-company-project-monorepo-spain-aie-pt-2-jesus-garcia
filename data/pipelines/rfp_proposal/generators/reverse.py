"""Generador de la sección económica de Reverse Logistics (Sofía Ramos)."""

from __future__ import annotations

from ..policy import RETURNS_MIN_HOURS
from ..rate_card import PENDING_PRICES, RETURNS_POLICY, REVERSE_PROCESS
from .base import DepartmentGenerator, sla_commitment


class ReverseGenerator(DepartmentGenerator):
    department_id = "reverse"
    label = "Reverse Logistics"
    responsible = "Sofía Ramos"
    service_label = "Logística inversa"
    prompt_guidance = (
        "La sección cubre el proceso de devoluciones, su coste y su tiempo de "
        "procesamiento. NUNCA prometas menos de 48 horas de procesamiento: es "
        "una restricción del briefing. Si la RFP no declara volumen o tasa de "
        "devoluciones, regístralo como pregunta abierta."
    )

    def department_fields(self, brief: dict) -> dict:
        return {
            "process": [dict(step) for step in REVERSE_PROCESS],
            "turnaround": {
                "minimum_hours": RETURNS_MIN_HOURS,
                "committed_hours": None,
                "owner": self.responsible,
                "notes": (
                    "Ventana estándar de devolución: "
                    f"{RETURNS_POLICY['window_days']} días desde la entrega. "
                    f"{RETURNS_POLICY['cost_note']} "
                    f"{RETURNS_POLICY['international_note']}"
                ),
            },
        }

    def pricing_rows(self, brief: dict) -> list[dict]:
        pending = PENDING_PRICES["reverse"]
        return [
            {
                "concept": pending["concept"],
                "unit": "devolución",
                "amount": None,
                "currency": brief.get("currency"),
                "owner": pending["owner"],
                "note": pending["note"],
                "status": "pendiente_confirmacion",
            }
        ]

    def sla(self, brief: dict) -> dict:
        return sla_commitment(
            detail=(
                "El SLA de entrega a tiempo del 90% mensual por país aplica a "
                "los envíos gestionados por TrackFlow, incluidas las etiquetas "
                "de devolución que TrackFlow emite."
            ),
            notes=[
                "El tiempo de procesamiento de devoluciones se compromete por "
                "separado y nunca por debajo de 48 horas.",
                "Las devoluciones internacionales requieren gestión manual del "
                "equipo de Reverse Logistics.",
            ],
        )


GENERATOR = ReverseGenerator()

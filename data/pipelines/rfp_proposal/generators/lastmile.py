"""Generador de la sección económica de Last Mile (Carlos Vega)."""

from __future__ import annotations

from ..policy import PEAK_EXTENSION_PCT
from ..rate_card import PENDING_PRICES, carrier_coverage, delivery_terms
from .base import DepartmentGenerator, sla_commitment


class LastMileGenerator(DepartmentGenerator):
    department_id = "lastmile"
    label = "Last Mile and Carrier Management"
    responsible = "Carlos Vega"
    service_label = "Última milla"
    prompt_guidance = (
        "La sección cubre coste por envío, transportistas disponibles según "
        "destino y SLA de entrega. No reveles tarifas negociadas con "
        "transportistas: solo el coste final ofrecido al cliente. Si la RFP no "
        "declara volumen o destinos, regístralo como pregunta abierta."
    )

    def department_fields(self, brief: dict) -> dict:
        return {"carriers": carrier_coverage(brief.get("client_country"))}

    def pricing_rows(self, brief: dict) -> list[dict]:
        pending = PENDING_PRICES["lastmile"]
        return [
            {
                "concept": "Coste por envío",
                "unit": "envío",
                "amount": None,
                "currency": brief.get("currency"),
                "owner": pending["owner"],
                "note": pending["note"],
                "status": "pendiente_confirmacion",
            }
        ]

    def sla(self, brief: dict) -> dict:
        terms = delivery_terms(brief.get("client_country"))
        detail = " ".join(
            [
                terms["standard"]["detail"],
                terms["express"]["detail"],
                terms["international"]["detail"],
                "SLA comprometido: 90% de entregas a tiempo al mes por país; "
                "dos meses consecutivos por debajo dan derecho a una "
                "compensación del 5% sobre la tarifa mensual del país.",
            ]
        )
        peak_note = (
            "TrackFlow no garantiza SLA en los días de alta demanda "
            "declarados (Black Friday, Navidad y rebajas de enero en España); "
            "esos días los tiempos pueden extenderse hasta un "
            f"{PEAK_EXTENSION_PCT}% adicional."
        )
        return sla_commitment(
            detail=detail,
            notes=[
                peak_note,
                "La selección de transportista la determina el sistema según "
                "destino, peso, tipo de producto y urgencia.",
            ],
        )


GENERATOR = LastMileGenerator()

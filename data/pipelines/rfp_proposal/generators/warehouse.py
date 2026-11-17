"""Generador de la sección económica de Warehouse Operations (Ana Whitfield)."""

from __future__ import annotations

from ..policy import (
    PREFERENTIAL_VOLUME_M3,
    STORAGE_GRACE_DAYS,
    STORAGE_LONG_TERM_DAYS,
    STORAGE_LONG_TERM_MULTIPLIER_PCT,
)
from ..rate_card import PENDING_PRICES, storage_rate
from .base import DepartmentGenerator, sla_commitment


class WarehouseGenerator(DepartmentGenerator):
    department_id = "warehouse"
    label = "Warehouse Operations"
    responsible = "Ana Whitfield"
    service_label = "Almacenamiento"
    prompt_guidance = (
        "La sección cubre capacidad de almacenamiento, coste por unidad de "
        "volumen y tiempo de onboarding. Apóyate en los SKUs y el volumen "
        "declarados en la RFP; si faltan, dilo como pregunta abierta. No "
        "inventes capacidades ni tiempos de puesta en marcha."
    )

    def department_fields(self, brief: dict) -> dict:
        rate = storage_rate(brief.get("client_country"))
        facts = brief.get("facts") or {}
        capacity = {
            "sku_count": facts.get("sku_count"),
            "storage_basis": (rate or {}).get("unit", "m³/mes"),
            "locations": [(rate or {}).get("location")] if rate else [],
            "notes": (
                "La capacidad comprometida debe validarse contra el volumen "
                "mensual y los SKUs declarados en la RFP."
            ),
        }
        onboarding = {
            "days": None,
            "owner": self.responsible,
            "steps": [
                "Integración con el sistema del cliente",
                "Alta de SKUs y ubicaciones",
                "Prueba de picking y packing",
            ],
        }
        return {"capacity": capacity, "onboarding": onboarding}

    def pricing_rows(self, brief: dict) -> list[dict]:
        currency = brief.get("currency")
        rate = storage_rate(brief.get("client_country"))
        rows: list[dict] = []
        if rate:
            rows.append(
                {
                    "concept": "Almacenamiento",
                    "unit": rate["unit"],
                    "amount": rate["amount"],
                    "currency": rate["currency"],
                    "basis": f"Tarifa estándar publicada ({rate['location']})",
                    "source": rate["source"],
                    "status": "ok",
                }
            )
        else:
            rows.append(
                {
                    "concept": "Almacenamiento",
                    "unit": "m³/mes",
                    "amount": None,
                    "currency": currency,
                    "owner": self.responsible,
                    "note": "Confirmar la tarifa aplicable al país del cliente.",
                    "status": "pendiente_confirmacion",
                }
            )
        pending = PENDING_PRICES["warehouse"]
        rows.append(
            {
                "concept": pending["concept"],
                "unit": "pallet/SKU",
                "amount": None,
                "currency": currency,
                "owner": pending["owner"],
                "note": pending["note"],
                "status": "pendiente_confirmacion",
            }
        )
        return rows

    def sla(self, brief: dict) -> dict:
        return sla_commitment(
            detail=(
                "TrackFlow se compromete a un 90% de entregas a tiempo al mes "
                "por país; si un país queda por debajo durante dos meses "
                "consecutivos, el cliente tiene derecho a una compensación del "
                "5% sobre la tarifa mensual de ese país."
            ),
            notes=[
                f"Los primeros {STORAGE_GRACE_DAYS} días de producto nuevo en "
                "inventario no generan cargo de almacenamiento.",
                f"El inventario con más de {STORAGE_LONG_TERM_DAYS} días sin "
                f"movimiento paga un {STORAGE_LONG_TERM_MULTIPLIER_PCT}% sobre "
                "la tarifa estándar.",
                f"Volúmenes superiores a {PREFERENTIAL_VOLUME_M3} m³ mensuales "
                "pueden negociar tarifa preferencial con Miguel Torres.",
            ],
        )


GENERATOR = WarehouseGenerator()

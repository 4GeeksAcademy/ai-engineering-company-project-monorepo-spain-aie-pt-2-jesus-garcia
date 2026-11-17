"""Política comercial de TrackFlow aplicada por los evaluadores.

Cada regla tiene un ``rule_id`` que apunta a la sección exacta del briefing
del Hito 9 (``docs/workflows/MILESTONE_9.md``) o al documento de política que
la concreta (``docs/workflows/RFP_PROPOSAL_POLICY.md``). El evaluador de
cumplimiento no inventa reglas: aplica esta lista cerrada.

Los límites de la tabla de descuentos por volumen no vienen dados por el
briefing (§5.4 solo exige que la tabla exista). Se documentan como política
interna de TrackFlow y quedan sujetos a validación de Miguel Torres.
"""

from __future__ import annotations

from typing import Final

from data.pipelines.rfp_intake.catalog import (
    COUNTRY_CURRENCY,
    currency_for_country,
    normalize_country,
)

BRIEFING_PATH: Final[str] = "docs/workflows/MILESTONE_9.md"
PROPOSAL_POLICY_PATH: Final[str] = "docs/workflows/RFP_PROPOSAL_POLICY.md"

# --- Reglas de negocio (MILESTONE_9 §5 y §2.3) -------------------------------

RULE_CURRENCY_BY_COUNTRY: Final[str] = "BRIEFING-5.1-CURRENCY"
RULE_DELIVERY_SLA: Final[str] = "BRIEFING-5.2-SLA-90"
RULE_RETURNS_MIN_48H: Final[str] = "BRIEFING-5.3-RETURNS-48H"
RULE_VOLUME_DISCOUNTS: Final[str] = "BRIEFING-5.4-VOLUME-DISCOUNTS"
RULE_CARRIER_RATES_CONFIDENTIAL: Final[str] = "BRIEFING-5.5-CARRIER-RATES-CONFIDENTIAL"
RULE_NO_INVENTED_FIGURES: Final[str] = "BRIEFING-2.3-NO-INVENTED-FIGURES"

RULES: Final[dict[str, dict]] = {
    RULE_CURRENCY_BY_COUNTRY: {
        "text": (
            "El precio se cotiza en USD para operación en Estados Unidos y en "
            "EUR para operación en España; lo determina `client_country`."
        ),
        "source": f"{BRIEFING_PATH} §5",
    },
    RULE_DELIVERY_SLA: {
        "text": (
            "Toda propuesta debe indicar el SLA de entrega a tiempo (%) que "
            "TrackFlow se compromete a cumplir (90% mensual por país)."
        ),
        "source": f"{BRIEFING_PATH} §5 + company-knowledge-base/trackflow-sla-delivery",
    },
    RULE_RETURNS_MIN_48H: {
        "text": (
            "Ninguna propuesta puede prometer procesamiento de devoluciones en "
            "menos de 48 horas."
        ),
        "source": f"{BRIEFING_PATH} §5",
    },
    RULE_VOLUME_DISCOUNTS: {
        "text": "Toda propuesta debe incluir una tabla de descuentos por volumen.",
        "source": f"{BRIEFING_PATH} §5",
    },
    RULE_CARRIER_RATES_CONFIDENTIAL: {
        "text": (
            "Ninguna propuesta puede revelar tarifas negociadas con "
            "transportistas específicos: solo el coste final ofrecido al cliente."
        ),
        "source": f"{BRIEFING_PATH} §5",
    },
    RULE_NO_INVENTED_FIGURES: {
        "text": (
            "No se inventan pallets, SKUs, pedidos, capacidades ni tarifas que "
            "no consten en la RFP, los metadatos canónicos o la tarifa publicada."
        ),
        "source": f"{BRIEFING_PATH} §2.3",
    },
}

# --- Valores canónicos -------------------------------------------------------

SLA_ON_TIME_PCT: Final[float] = 90.0
RETURNS_MIN_HOURS: Final[int] = 48
RETURNS_WINDOW_DAYS: Final[int] = 30
STORAGE_GRACE_DAYS: Final[int] = 30
STORAGE_LONG_TERM_DAYS: Final[int] = 180
STORAGE_LONG_TERM_MULTIPLIER_PCT: Final[int] = 150
PREFERENTIAL_VOLUME_M3: Final[int] = 50

DELIVERY_STANDARD_DAYS: Final[tuple[int, int]] = (3, 5)
DELIVERY_EXPRESS_HOURS: Final[tuple[int, int]] = (24, 48)
DELIVERY_INTERNATIONAL_DAYS: Final[tuple[int, int]] = (7, 12)
SLA_COMPENSATION_PCT: Final[int] = 5
PEAK_EXTENSION_PCT: Final[int] = 40

# Tabla de descuentos por volumen (política interna, ver PROPOSAL_POLICY_PATH).
# (min_pedidos_mes, max_pedidos_mes | None, descuento_%)
VOLUME_DISCOUNT_TIERS: Final[tuple[tuple[int, int | None, int], ...]] = (
    (0, 1_999, 0),
    (2_000, 4_999, 3),
    (5_000, 9_999, 6),
    (10_000, None, 10),
)

# --- Formato obligatorio por departamento (MILESTONE_9 §2.1) -----------------

DEPARTMENT_REQUIRED_BLOCKS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "warehouse": (
        ("capacity", "capacidad de almacenamiento"),
        ("pricing", "coste por pallet/SKU o unidad de volumen"),
        ("onboarding", "tiempo de onboarding"),
        ("discount_tiers", "tabla de descuentos por volumen"),
        ("sla", "SLA de entrega a tiempo"),
    ),
    "lastmile": (
        ("carriers", "transportistas disponibles según destino"),
        ("pricing", "coste por envío"),
        ("sla", "SLA de entrega a tiempo"),
        ("discount_tiers", "tabla de descuentos por volumen"),
    ),
    "reverse": (
        ("process", "proceso de devoluciones"),
        ("pricing", "coste de procesamiento de devoluciones"),
        ("turnaround", "tiempo de procesamiento (mínimo 48 h)"),
        ("discount_tiers", "tabla de descuentos por volumen"),
        ("sla", "SLA de entrega a tiempo"),
    ),
}


def format_rule_id(department_id: str) -> str:
    return f"BRIEFING-2.1-FORMAT-{department_id.upper()}"


def expected_currency(client_country: str | None) -> str | None:
    """Moneda canónica del país. Nunca adivina: sin país, sin moneda."""

    country = normalize_country(client_country) if client_country else None
    if country is None:
        return None
    return currency_for_country(country)


def currency_country_table() -> dict[str, str]:
    return dict(COUNTRY_CURRENCY)


def policy_numbers() -> set[str]:
    """Cifras que un borrador puede usar por política, no por la RFP."""

    numbers = {
        str(SLA_ON_TIME_PCT).split(".")[0],
        str(RETURNS_MIN_HOURS),
        str(RETURNS_WINDOW_DAYS),
        str(STORAGE_GRACE_DAYS),
        str(STORAGE_LONG_TERM_DAYS),
        str(STORAGE_LONG_TERM_MULTIPLIER_PCT),
        str(PREFERENTIAL_VOLUME_M3),
        str(SLA_COMPENSATION_PCT),
        str(PEAK_EXTENSION_PCT),
    }
    for start, end in DELIVERY_STANDARD_DAYS, DELIVERY_INTERNATIONAL_DAYS:
        numbers.update({str(start), str(end)})
    for start, end in (DELIVERY_EXPRESS_HOURS,):
        numbers.update({str(start), str(end)})
    for minimum, maximum, discount in VOLUME_DISCOUNT_TIERS:
        numbers.add(str(minimum))
        if maximum is not None:
            numbers.add(str(maximum))
        numbers.add(str(discount))
    return numbers


def discount_tier_rows() -> list[dict]:
    """Tramos serializables listos para el generador y la base de datos."""

    rows: list[dict] = []
    for minimum, maximum, discount in VOLUME_DISCOUNT_TIERS:
        rows.append(
            {
                "min_monthly_volume": minimum,
                "max_monthly_volume": maximum,
                "discount_pct": discount,
                "notes": (
                    "Descuento sujeto a aprobación de Miguel Torres."
                    if discount > 0
                    else "Tarifa estándar publicada."
                ),
            }
        )
    return rows

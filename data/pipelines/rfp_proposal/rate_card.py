"""Tarifa y cobertura publicadas de TrackFlow.

Fuente: ``docs/company-knowledge-base/``. Es la única fuente de precios que
puede usar el generador: lo que no está publicado se marca como pendiente de
confirmación y viaja como pregunta abierta. Nunca se estima.
"""

from __future__ import annotations

from typing import Final

from .policy import (
    DELIVERY_EXPRESS_HOURS,
    DELIVERY_INTERNATIONAL_DAYS,
    DELIVERY_STANDARD_DAYS,
    RETURNS_WINDOW_DAYS,
)

KB_PATH: Final[str] = "docs/company-knowledge-base"

STORAGE_RATES: Final[dict[str, dict]] = {
    "US": {
        "amount": 18.0,
        "currency": "USD",
        "unit": "m³/mes",
        "location": "Los Ángeles",
        "source": f"{KB_PATH}/trackflow-storage-pricing.es.md",
    },
    "Spain": {
        "amount": 16.0,
        "currency": "EUR",
        "unit": "m³/mes",
        "location": "Zaragoza",
        "source": f"{KB_PATH}/trackflow-storage-pricing.es.md",
    },
}

CARRIER_COVERAGE: Final[dict[str, tuple[dict, ...]]] = {
    "US": (
        {
            "carrier": "UPS",
            "coverage": "Cobertura nacional completa en Estados Unidos",
            "strength": "Mejor tarifa para paquetes de más de 5 kg",
        },
        {
            "carrier": "FedEx",
            "coverage": "Cobertura nacional en Estados Unidos",
            "strength": "Mejor tiempo express dentro de California",
        },
        {
            "carrier": "DHL",
            "coverage": "Cobertura internacional desde Los Ángeles",
            "strength": "Única opción fiable para envíos internacionales",
        },
    ),
    "Spain": (
        {
            "carrier": "MRW",
            "coverage": "Cobertura nacional en España",
            "strength": "Tarifas competitivas para paquetes de menos de 2 kg",
        },
        {
            "carrier": "SEUR",
            "coverage": "Cobertura nacional en España",
            "strength": "Mejor cobertura en zonas rurales de Aragón",
        },
        {
            "carrier": "DHL",
            "coverage": "Cobertura internacional desde España",
            "strength": "Envíos internacionales",
        },
        {
            "carrier": "Transportistas locales de Zaragoza",
            "coverage": "Solo área metropolitana de Zaragoza",
            "strength": "Última milla local; no cubren el resto de España",
        },
    ),
}


def storage_rate(client_country: str | None) -> dict | None:
    if not client_country:
        return None
    return STORAGE_RATES.get(client_country)


def carrier_coverage(client_country: str | None) -> list[dict]:
    if not client_country:
        return []
    return [dict(item) for item in CARRIER_COVERAGE.get(client_country, ())]


def delivery_terms(client_country: str | None) -> dict:
    country = client_country or "el país de operación"
    return {
        "standard": {
            "min_days": DELIVERY_STANDARD_DAYS[0],
            "max_days": DELIVERY_STANDARD_DAYS[1],
            "detail": (
                f"Envío estándar en {country}: "
                f"{DELIVERY_STANDARD_DAYS[0]} a {DELIVERY_STANDARD_DAYS[1]} "
                "días hábiles dentro del mismo país."
            ),
        },
        "express": {
            "min_hours": DELIVERY_EXPRESS_HOURS[0],
            "max_hours": DELIVERY_EXPRESS_HOURS[1],
            "detail": (
                "Envío express en "
                f"{DELIVERY_EXPRESS_HOURS[0]}-{DELIVERY_EXPRESS_HOURS[1]} horas, "
                "disponible solo en zonas metropolitanas (Los Ángeles y área "
                "Zaragoza-Madrid)."
            ),
        },
        "international": {
            "min_days": DELIVERY_INTERNATIONAL_DAYS[0],
            "max_days": DELIVERY_INTERNATIONAL_DAYS[1],
            "detail": (
                f"Envío internacional en {DELIVERY_INTERNATIONAL_DAYS[0]} a "
                f"{DELIVERY_INTERNATIONAL_DAYS[1]} días hábiles, sujeto a aduana."
            ),
        },
    }


REVERSE_PROCESS: Final[tuple[dict, ...]] = (
    {
        "step": 1,
        "detail": "El cliente final solicita la devolución en el portal de la marca.",
    },
    {
        "step": 2,
        "detail": (
            "TrackFlow genera la etiqueta de devolución si el motivo está dentro "
            "de las reglas configuradas por la marca cliente."
        ),
    },
    {
        "step": 3,
        "detail": (
            "El producto llega al almacén y un operativo lo inspecciona y "
            "clasifica: apto para reventa, apto para reacondicionar o no apto."
        ),
    },
    {
        "step": 4,
        "detail": (
            "TrackFlow ejecuta la logística según las reglas de la marca; no "
            "reacondiciona ni revende producto por cuenta propia."
        ),
    },
)

RETURNS_POLICY: Final[dict] = {
    "window_days": RETURNS_WINDOW_DAYS,
    "cost_note": (
        "El coste del envío de vuelta lo asume la marca cliente, salvo error de "
        "TrackFlow (producto dañado en tránsito o entrega equivocada)."
    ),
    "international_note": (
        "Las devoluciones internacionales requieren gestión manual del equipo "
        "de Sofía Ramos."
    ),
}

# Precios que no están publicados en la base de conocimiento: se declaran
# pendientes con el responsable que debe confirmarlos.
PENDING_PRICES: Final[dict[str, dict]] = {
    "warehouse": {
        "concept": "Coste por pallet/SKU y tiempo de onboarding",
        "owner": "Ana Whitfield",
        "note": "Pendiente de confirmación por Warehouse Operations.",
    },
    "lastmile": {
        "concept": "Coste por envío",
        "owner": "Carlos Vega",
        "note": (
            "Pendiente de confirmación por Last Mile. Solo se publica el coste "
            "final ofrecido al cliente."
        ),
    },
    "reverse": {
        "concept": "Coste de procesamiento de devoluciones",
        "owner": "Sofía Ramos",
        "note": "Pendiente de confirmación por Reverse Logistics.",
    },
}

def rate_card_numbers() -> set[str]:
    """Cifras publicadas que el guardarraíl numérico puede aceptar."""

    numbers: set[str] = set()
    for rate in STORAGE_RATES.values():
        numbers.add(f"{rate['amount']:.0f}")
    return numbers

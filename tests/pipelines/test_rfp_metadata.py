"""Tests de extracción y normalización de metadatos RFP."""

from __future__ import annotations

from data.pipelines.rfp_intake.metadata import (
    extract_metadata,
    normalize_metadata,
    parse_deadline,
    parse_int,
    parse_rate,
)
from rfp_support import MODAVIVA, ScriptedLlm, luna_classification, modaviva_classification


def test_parse_volume_with_thousands_separators():
    assert parse_int("5,000 orders a month") == 5000
    assert parse_int("5.000 pedidos/mes") == 5000
    assert parse_int("15.000 SKUs") == 15000
    assert parse_int("sin cifra") is None
    assert parse_int("0") is None


def test_parse_rate_and_deadline():
    assert parse_rate("18%") == 18
    assert parse_rate("18,5 %") == 18.5
    assert parse_rate("120%") is None
    assert parse_deadline("August 28, 2026") == "2026-08-28"
    assert parse_deadline("August 24th") == "2026-08-24"
    assert parse_deadline("28 de agosto de 2026") == "2026-08-28"
    assert parse_deadline("3 semanas") is None


def test_country_determines_currency_and_missing_data_is_not_invented():
    metadata = normalize_metadata(
        {
            "client_name": "ModaViva, S.L.",
            "client_country": "España",
            "services_requested": ["warehousing", "reverse_logistics"],
            "monthly_volume": None,
            "deadline": "2026-08-28",
            "budget_range": None,
        },
        modaviva_classification(),
        MODAVIVA,
    )
    assert metadata["client_country"] == "Spain"
    assert metadata["currency"] == "EUR"
    assert metadata["monthly_volume"] is None
    assert metadata["sku_count"] == 15000
    assert "monthly_volume" in metadata["missing_fields"]
    assert "budget_range" in metadata["missing_fields"]


def test_monthly_volume_is_extracted_from_informal_request():
    metadata = normalize_metadata(
        {
            "client_name": "Luna Cosmetics",
            "client_country": "US",
            "services_requested": ["warehousing", "last_mile"],
            "deadline": "2026-08-24",
        },
        luna_classification(),
        "We just crossed 5,000 orders a month and need warehousing and shipping.",
    )
    assert metadata["client_country"] == "US"
    assert metadata["currency"] == "USD"
    assert metadata["monthly_volume"] == 5000


def test_extract_metadata_uses_llm_but_normalizes_services():
    llm = ScriptedLlm(
        metadata={
            "client_name": "ModaViva, S.L.",
            "client_country": "Spain",
            "services_requested": ["warehousing", "returns"],
            "monthly_volume": None,
            "sku_count": 15000,
            "deadline": "2026-08-28",
            "budget_range": None,
            "missing_fields": ["monthly_volume"],
        }
    )
    metadata = extract_metadata(MODAVIVA, modaviva_classification(), llm)
    assert metadata["services_requested"] == [
        "warehousing",
        "reverse_logistics",
    ]
    assert metadata["departments_needed"] == ["warehouse", "reverse"]
    assert metadata["currency"] == "EUR"

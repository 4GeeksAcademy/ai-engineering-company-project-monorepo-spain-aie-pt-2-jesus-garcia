"""Tests del agente clasificador de RFPs."""

from __future__ import annotations

import pytest

from data.pipelines.rfp_intake.classifier import (
    ClassifierError,
    classify_document,
    detect_vendor_pitch,
    normalize_classification,
)
from data.pipelines.rfp_intake.llm import LlmError
from rfp_support import MODAVIVA, RAPIDSHIP, ScriptedLlm


def test_vendor_pitch_is_detected_before_calling_the_llm():
    llm = ScriptedLlm()
    result = classify_document(RAPIDSHIP, llm)
    assert result["is_rfp"] is False
    assert result["document_type"] == "carrier_pitch"
    assert llm.calls == []


def test_vendor_pitch_does_not_flag_real_rfps():
    assert detect_vendor_pitch(MODAVIVA) is False


def test_formal_rfp_is_classified_and_canonicalized():
    llm = ScriptedLlm(
        classifier={
            "is_rfp": True,
            "confidence": "0.91",
            "document_type": "formal_rfp",
            "reason": "Solicita almacenamiento y devoluciones.",
            "client_name": "ModaViva, S.L.",
            "client_country": "España",
            "services_requested": ["warehousing", "devoluciones"],
            "unknown_services": [],
            "evidence": ["15.000 SKUs"],
        }
    )
    result = classify_document(MODAVIVA, llm)
    assert result["is_rfp"] is True
    assert result["confidence"] == pytest.approx(0.91)
    assert result["client_country"] == "Spain"
    assert result["services_requested"] == ["warehousing", "reverse_logistics"]
    assert result["departments_needed"] == ["warehouse", "reverse"]


def test_informal_request_can_be_a_rfp():
    llm = ScriptedLlm(
        classifier={
            "is_rfp": True,
            "confidence": 0.88,
            "document_type": "informal_request",
            "reason": "Email pidiendo 3PL.",
            "client_name": "Luna Cosmetics",
            "client_country": "Los Angeles",
            "services_requested": ["warehousing", "shipping"],
            "unknown_services": [],
            "evidence": ["Looking for a 3PL partner"],
        }
    )
    result = classify_document("Luna Cosmetics\nWe need warehousing and shipping.", llm)
    assert result["is_rfp"] is True
    assert result["client_country"] == "US"
    assert result["departments_needed"] == ["warehouse", "lastmile"]


def test_invalid_llm_json_raises_instead_of_silently_discarding():
    class BrokenLlm:
        def __call__(self, messages, **kwargs):
            raise LlmError("JSON inválido")

    with pytest.raises(ClassifierError):
        classify_document(MODAVIVA, BrokenLlm())


def test_normalize_classification_requires_boolean_is_rfp():
    with pytest.raises(ClassifierError):
        normalize_classification({"reason": "sin campo"})


def test_unknown_services_are_preserved_not_converted_to_departments():
    result = normalize_classification(
        {
            "is_rfp": True,
            "confidence": 0.7,
            "reason": "Pide almacenamiento y aduanas.",
            "services_requested": ["warehousing", "customs brokerage"],
            "unknown_services": ["customs brokerage"],
            "client_country": "US",
        }
    )
    assert result["services_requested"] == ["warehousing"]
    assert result["unknown_services"] == ["customs brokerage"]
    assert result["departments_needed"] == ["warehouse"]

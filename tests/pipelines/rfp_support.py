"""Fixtures compartidas por los tests del pipeline ``rfp_intake``."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from data.pipelines.rfp_intake.runner import run_rfp_intake

MODAVIVA = """# REQUEST FOR PROPOSAL (RFP)
Solicitud de Propuesta — Almacenamiento y Gestión de Devoluciones

RFP Reference No.: MV-LOG-2026-03
Issuing Organization: ModaViva, S.L.
Date Issued: August 3, 2026
Proposal Due Date: August 28, 2026

## 1. Background
ModaViva es una marca de moda española con venta online en España y Portugal.
Buscamos un partner logístico para almacenamiento y gestión de devoluciones;
mantenemos nuestro propio transportista para el reparto de última milla.

## 2. Scope of Work / Services Requested
- Almacenamiento de aproximadamente 15.000 SKUs en un centro cercano a Zaragoza
- Gestión de devoluciones: inspección, reacondicionamiento y restock
- Integración con nuestro ERP vía API
- No se requiere gestión de transportistas ni última milla
"""

LUNA = """Luna Cosmetics — Los Angeles, CA, USA

Subject: Looking for a 3PL partner

Hi,

We're Luna Cosmetics, a small direct-to-consumer skincare brand out of LA.
We just crossed 5,000 orders a month and it's not sustainable anymore.

We need someone to handle warehousing and shipping for us across the US —
ideally someone who can also handle carrier selection since we don't have
relationships with any carriers yet.

Could you send over a proposal? We're hoping to be up and running within the
next 3 weeks (around August 24th).

Best,
Maya Chen
Founder, Luna Cosmetics
"""

RAPIDSHIP = """Subject: Exclusive shipping rates for TrackFlow

Hello,

This is Jake from RapidShip Carriers. We'd love the opportunity to become one of
TrackFlow's preferred carrier partners. We're currently offering aggressive
introductory rates for new partners handling over 10,000 packages/month.

Let me know if you'd like to set up a call to go over pricing.

Best,
Jake Fenwick
Partnerships, RapidShip Carriers
"""


def modaviva_classification() -> dict:
    return {
        "is_rfp": True,
        "confidence": 0.96,
        "document_type": "formal_rfp",
        "reason": "RFP formal de ModaViva para almacenamiento y devoluciones.",
        "client_name": "ModaViva, S.L.",
        "client_country": "Spain",
        "services_requested": ["warehousing", "reverse_logistics"],
        "unknown_services": [],
        "departments_needed": ["warehouse", "reverse"],
        "evidence": ["Almacenamiento de aproximadamente 15.000 SKUs"],
    }


def modaviva_metadata() -> dict:
    return {
        "client_name": "ModaViva, S.L.",
        "client_country": "Spain",
        "currency": "EUR",
        "language": "es",
        "services_requested": ["warehousing", "reverse_logistics"],
        "unknown_services": [],
        "monthly_volume": None,
        "sku_count": 15_000,
        "return_volume": None,
        "return_rate": None,
        "deadline": "2026-08-28",
        "budget_range": None,
        "contact": {"name": "Elena Bosch"},
        "scope_notes": ["15.000 SKUs", "transportista propio"],
        "evidence": ["15.000 SKUs"],
        "missing_fields": ["monthly_volume", "budget_range"],
    }


def luna_classification() -> dict:
    return {
        "is_rfp": True,
        "confidence": 0.93,
        "document_type": "informal_request",
        "reason": "Email de una marca pidiendo 3PL, warehousing y shipping.",
        "client_name": "Luna Cosmetics",
        "client_country": "US",
        "services_requested": ["warehousing", "last_mile"],
        "unknown_services": [],
        "departments_needed": ["warehouse", "lastmile"],
        "evidence": ["We need someone to handle warehousing and shipping"],
    }


def luna_metadata() -> dict:
    return {
        "client_name": "Luna Cosmetics",
        "client_country": "US",
        "currency": "USD",
        "language": "en",
        "services_requested": ["warehousing", "last_mile"],
        "unknown_services": [],
        "monthly_volume": 5_000,
        "sku_count": None,
        "return_volume": None,
        "return_rate": None,
        "deadline": "2026-08-24",
        "budget_range": None,
        "contact": {"name": "Maya Chen", "role": "Founder"},
        "scope_notes": ["carrier selection"],
        "evidence": ["5,000 orders a month"],
        "missing_fields": ["budget_range"],
    }


def worker_response(aspect: str = "Almacenamiento") -> dict:
    return {
        "key_aspects": [
            {
                "aspect": aspect,
                "detail": "La RFP declara 15.000 SKUs y devoluciones.",
                "evidence": "15.000 SKUs",
                "confidence": "high",
            }
        ],
        "open_questions": [],
        "assumed_facts": {
            "monthly_volume": None,
            "currency": "EUR",
            "client_country": "Spain",
        },
    }


class ScriptedLlm:
    """LLM falso que responde según el marcador del system prompt."""

    _MARKERS = (
        ("clasificador de entrada", "classifier"),
        ("extractor de metadatos", "metadata"),
        ("orquestador de propuestas", "orchestrator"),
        ("synthesizer de propuestas", "synthesizer"),
    )

    def __init__(self, **responses):
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, messages, *, max_tokens=1_200, temperature=0.0):
        system = messages[0].get("content", "") if messages else ""
        for marker, key in self._MARKERS:
            if marker in system:
                self.calls.append(key)
                return copy.deepcopy(self.responses.get(key))
        if "responsable de" in system:
            self.calls.append("worker")
            for department, response in self.responses.get("workers", {}).items():
                if department in system:
                    return copy.deepcopy(response)
            default = self.responses.get("worker")
            if default is not None:
                return copy.deepcopy(default)
        raise AssertionError(f"El LLM falso no tiene respuesta para: {system[:120]}")


class InMemoryRepo:
    def __init__(self, *, ticket_id: str = "ticket-1") -> None:
        self.ticket = {
            "ticket_id": ticket_id,
            "rfp_id": "RFP-TEST-1",
            "status": "analizando",
            "raw_pdf_path": str(Path(tempfile.mkdtemp(prefix="rfp-test-")) / "rfp.pdf"),
            "markdown_path": None,
            "pipeline_stage": None,
        }
        self.markdown_path: str | None = None
        self.document_metadata: dict = {}
        self.readability: dict = {}
        self.metadata: dict = {}
        self.plan: list[str] = []
        self.sections: dict[str, dict] = {}
        self.discard_kwargs: dict = {}
        self.handoff: dict = {}
        self.failure: dict = {}
        self.stages: list[str] = []

    def get_ticket(self, ticket_id: str) -> dict:
        return dict(self.ticket)

    def mark_processing(self, ticket_id: str) -> None:
        self.ticket["status"] = "analizando"
        self.ticket["pipeline_stage"] = "iniciado"

    def set_stage(self, ticket_id: str, stage: str) -> None:
        self.ticket["pipeline_stage"] = stage
        self.stages.append(stage)

    def save_conversion(
        self,
        ticket_id: str,
        *,
        markdown_path: str,
        document_metadata: dict,
        readability: dict,
    ) -> None:
        self.ticket["markdown_path"] = markdown_path
        self.markdown_path = markdown_path
        self.document_metadata = document_metadata
        self.readability = readability

    def save_metadata(self, ticket_id: str, *, metadata: dict, classification: dict) -> None:
        self.metadata = metadata
        self.classification = classification

    def save_plan(self, ticket_id: str, *, departments: list[str]) -> None:
        self.plan = departments

    def save_section(self, ticket_id: str, *, section: dict) -> None:
        self.sections[section["department_id"]] = section

    def discard(
        self,
        ticket_id: str,
        *,
        reason: str,
        classification: dict,
        stage: str = "descartado",
    ) -> None:
        self.ticket["status"] = "descartado"
        self.ticket["pipeline_stage"] = stage
        self.discard_kwargs = {"reason": reason, "classification": classification}

    def complete(self, ticket_id: str, *, handoff: dict, stage: str = "completado") -> None:
        self.ticket["status"] = "analisis_completo"
        self.ticket["pipeline_stage"] = stage
        self.handoff = handoff

    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        self.ticket["status"] = "error"
        self.ticket["pipeline_stage"] = stage
        self.failure = {"stage": stage, "error": error}


def run_pipeline(markdown: str, *, repo=None, llm=None, **responses):
    repo = repo or InMemoryRepo()
    llm = llm or ScriptedLlm(**responses)
    state = run_rfp_intake(
        "ticket-1",
        repo,
        llm=llm,
        converter=lambda pdf_path, markdown_path: {
            "markdown": markdown,
            "markdown_path": str(markdown_path),
            "document_metadata": {"page_count": 1, "converter": "test"},
        },
    )
    return repo, state, llm


def channel_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[2]
    base = root / "docs" / "workflows" / "rfp-requests"
    return (
        base / "trackflow-request-1.pdf",
        base / "trackflow-request-2.pdf",
        base / "trackflow-request-3.pdf",
    )

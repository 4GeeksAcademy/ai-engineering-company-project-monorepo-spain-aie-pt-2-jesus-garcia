"""Fixtures compartidas por los tests del pipeline ``rfp_proposal``."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from data.pipelines.rfp_intake.synthesizer import build_handoff
from data.pipelines.rfp_proposal import run_proposal_generation

MODAVIVA_METADATA = {
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

LUNA_METADATA = {
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


def _section(
    *,
    department_id: str,
    label: str,
    responsible: str,
    aspects: list[tuple[str, str, str]],
    questions: list[str],
    currency: str,
    country: str,
) -> dict:
    return {
        "department_id": department_id,
        "department_label": label,
        "responsible": responsible,
        "focus": f"Foco de {label}",
        "key_aspects": [
            {
                "aspect": aspect,
                "detail": detail,
                "evidence": evidence,
                "confidence": "high",
            }
            for aspect, detail, evidence in aspects
        ],
        "open_questions": questions,
        "assumed_facts": {
            "monthly_volume": None,
            "currency": currency,
            "client_country": country,
        },
        "unsupported_claims": [],
        "conflicts": [],
        "source_excerpts": [],
    }


def modaviva_sections() -> dict[str, dict]:
    return {
        "warehouse": _section(
            department_id="warehouse",
            label="Warehouse Operations",
            responsible="Ana Whitfield",
            aspects=[
                (
                    "Volumen de SKUs",
                    "La RFP declara 15.000 SKUs en un centro cercano a Zaragoza.",
                    "Almacenamiento de aproximadamente 15.000 SKUs",
                )
            ],
            questions=["Falta el volumen mensual de pedidos: confirmarlo."],
            currency="EUR",
            country="Spain",
        ),
        "reverse": _section(
            department_id="reverse",
            label="Reverse Logistics",
            responsible="Sofía Ramos",
            aspects=[
                (
                    "Gestión de devoluciones",
                    "La RFP pide inspección, reacondicionamiento y restock.",
                    "Gestión de devoluciones: inspección y restock",
                )
            ],
            questions=["Falta la tasa de devoluciones: confirmarlo."],
            currency="EUR",
            country="Spain",
        ),
    }


def luna_sections() -> dict[str, dict]:
    return {
        "warehouse": _section(
            department_id="warehouse",
            label="Warehouse Operations",
            responsible="Ana Whitfield",
            aspects=[
                (
                    "Volumen mensual",
                    "Luna declara 5.000 pedidos al mes, con 15.000 SKUs.",
                    "5,000 orders a month",
                )
            ],
            questions=["Confirmar cuántos SKUs distintos almacenar."],
            currency="USD",
            country="US",
        ),
        "lastmile": _section(
            department_id="lastmile",
            label="Last Mile and Carrier Management",
            responsible="Carlos Vega",
            aspects=[
                (
                    "Cobertura de transportistas",
                    "Luna no tiene transportistas propios en Estados Unidos.",
                    "we don't have relationships with any carriers yet",
                )
            ],
            questions=["Confirmar zonas de reparto prioritarias en EE. UU."],
            currency="USD",
            country="US",
        ),
    }


def _handoff(
    *,
    metadata: dict,
    sections: dict[str, dict],
    ticket_id: str = "ticket-1",
) -> dict:
    empty = Path(tempfile.mkdtemp(prefix="rfp-proposal-"))
    return build_handoff(
        ticket_id=ticket_id,
        rfp_id="RFP-TEST-1",
        metadata=metadata,
        sections=sections,
        classification={
            "document_type": "formal_rfp",
            "confidence": 0.96,
            "reason": "RFP de TrackFlow.",
        },
        readability={"word_count": 120, "estimated_llm_tokens": 240},
        document_metadata={"page_count": 1, "converter": "test"},
        pdf_path=str(empty / "missing.pdf"),
        markdown_path=str(empty / "missing.md"),
        llm=None,
    )


def modaviva_handoff(ticket_id: str = "ticket-1") -> dict:
    return _handoff(
        metadata=MODAVIVA_METADATA,
        sections=modaviva_sections(),
        ticket_id=ticket_id,
    )


def luna_handoff(ticket_id: str = "ticket-1") -> dict:
    return _handoff(
        metadata=LUNA_METADATA,
        sections=luna_sections(),
        ticket_id=ticket_id,
    )


def warehouse_only_handoff(ticket_id: str = "ticket-1") -> dict:
    return _handoff(
        metadata=MODAVIVA_METADATA,
        sections={"warehouse": modaviva_sections()["warehouse"]},
        ticket_id=ticket_id,
    )


# --- LLM falso ---------------------------------------------------------------

_GENERATOR_LABELS = {
    "Warehouse Operations": "warehouse",
    "Last Mile and Carrier Management": "lastmile",
    "Reverse Logistics": "reverse",
}


def prose(
    *,
    aspects: list[str],
    summary: str | None = None,
    offerings: list[dict] | None = None,
    assumptions: list[str] | None = None,
    questions: list[str] | None = None,
) -> dict:
    """Prosa por defecto suficientemente larga y legible para pasar el umbral."""

    return {
        "executive_summary": summary
        or (
            "TrackFlow plantea una operación adaptada al volumen declarado por "
            "el cliente. El servicio incluye un interlocutor dedicado, "
            "seguimiento operativo y una revisión mensual de los indicadores "
            "acordados. La propuesta se apoya en la tarifa publicada y en los "
            "datos que el cliente ha compartido durante la fase de análisis. "
            "Cualquier dato pendiente se confirma antes de firmar el contrato."
        ),
        "offerings": offerings
        or [
            {
                "name": "Servicio dedicado",
                "detail": (
                    "Un equipo asignado a la cuenta revisa la operación cada "
                    "semana y propone mejoras sobre los datos del cliente."
                ),
            }
        ],
        "assumptions": assumptions
        or ["La tarifa publicada se aplica sobre el volumen ocupado."],
        "additional_open_questions": questions or [],
        "addresses_aspects": aspects,
    }


class ScriptedProposalLlm:
    """LLM falso con respuestas por departamento y por iteración."""

    def __init__(
        self,
        *,
        generators: dict[str, list[dict] | dict] | None = None,
        relevance: list[dict] | dict | None = None,
    ) -> None:
        self.generators = {
            department: (
                value if isinstance(value, list) else [value]
            )
            for department, value in (generators or {}).items()
        }
        self.relevance = (
            relevance if isinstance(relevance, list) else [relevance or {}]
        )
        self.generator_calls: list[str] = []
        self.relevance_calls = 0
        self.messages: list[list[dict]] = []

    def _next(self, queue: list[dict], index: int) -> dict:
        return copy.deepcopy(queue[min(index, len(queue) - 1)])

    def __call__(self, messages, *, max_tokens=1_200, temperature=0.0):
        system = messages[0].get("content", "") if messages else ""
        self.messages.append(messages)
        if "generador de la sección de propuesta" in system:
            for label, department in _GENERATOR_LABELS.items():
                if label in system:
                    self.generator_calls.append(department)
                    queue = self.generators.get(department)
                    if not queue:
                        raise AssertionError(
                            f"Sin respuesta de generador para {department}"
                        )
                    index = self.generator_calls.count(department) - 1
                    return self._next(queue, index)
            raise AssertionError(f"Generador sin departamento: {system[:120]}")
        if "evaluador de pertinencia" in system:
            response = self._next(self.relevance, self.relevance_calls)
            self.relevance_calls += 1
            return response
        raise AssertionError(f"El LLM falso no tiene respuesta para: {system[:120]}")


# --- Repositorio en memoria --------------------------------------------------

STATUS_ORDER = {
    "analisis_completo": 1,
    "generando_borrador": 2,
    "en_evaluación": 3,
    "needs_human_review": 4,
    "esperando_aprobación": 5,
}


class InMemoryProposalRepo:
    def __init__(self, handoff: dict, *, ticket_id: str = "ticket-1") -> None:
        self.ticket = {
            "ticket_id": ticket_id,
            "rfp_id": handoff.get("rfp_id") or "RFP-TEST-1",
            "status": "analisis_completo",
            "handoff_status": "ready",
            "handoff_payload": copy.deepcopy(handoff),
            "proposal_stage": None,
        }
        self.sections: dict[str, dict] = {}
        self.evaluations: list[tuple[str, dict]] = []
        self.drafts: list[tuple[str, int, dict]] = []
        self.status_history: list[str] = []
        self.stages: list[str] = []
        self.proposal_handoff: dict = {}
        self.failure: dict = {}

    def get_ticket(self, ticket_id: str) -> dict:
        return dict(self.ticket)

    def get_rfp_facts(self, ticket_id: str) -> dict:
        return {}

    def set_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        stage: str | None = None,
        force: bool = False,
    ) -> None:
        current = self.ticket.get("status")
        if not force:
            if STATUS_ORDER.get(status, 0) < STATUS_ORDER.get(current, 0):
                return
        self.ticket["status"] = status
        if stage:
            self.ticket["proposal_stage"] = stage
            self.stages.append(stage)
        self.status_history.append(status)

    def save_draft(
        self,
        ticket_id: str,
        *,
        department_id: str,
        draft: dict,
        iteration: int,
    ) -> None:
        self.drafts.append((department_id, iteration, copy.deepcopy(draft)))
        self.sections.setdefault(department_id, {})["draft"] = copy.deepcopy(draft)

    def save_evaluation(
        self,
        ticket_id: str,
        *,
        department_id: str,
        evaluation: dict,
    ) -> None:
        self.evaluations.append((department_id, copy.deepcopy(evaluation)))
        self.sections.setdefault(department_id, {})["evaluation"] = copy.deepcopy(
            evaluation
        )

    def save_section_status(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        review_reason: str | None = None,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["status"] = status
        if review_reason:
            section["review_reason"] = review_reason

    def complete_proposal(
        self,
        ticket_id: str,
        *,
        handoff: dict,
        status: str,
    ) -> None:
        self.ticket["status"] = status
        self.proposal_handoff = handoff
        self.status_history.append(status)

    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        self.ticket["status"] = "error"
        self.failure = {"stage": stage, "error": error}


def run_proposal(handoff: dict, *, llm=None, repo=None, max_iterations: int = 2):
    repo = repo or InMemoryProposalRepo(handoff)
    result = run_proposal_generation(
        repo.ticket["ticket_id"],
        repo,
        llm=llm,
        max_iterations=max_iterations,
    )
    return repo, result

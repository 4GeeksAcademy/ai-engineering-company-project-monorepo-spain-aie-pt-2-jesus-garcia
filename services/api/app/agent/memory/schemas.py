"""Contratos Pydantic de la memoria del agente (sin acceso a base de datos)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MemoryType = Literal["carrier_rule", "operational_context", "client_preference"]
ScopeKind = Literal["carrier", "ops", "client"]
IntentLabel = Literal["approve", "reject", "edit", "unrelated"]


class MemoryScope(BaseModel):
    """Alcance normalizado y acotado de un hecho memorizable.

    No existe un alcance global: todo hecho queda limitado a un carrier, una
    ruta/almacén o un cliente B2B. Así el daño de una entrada falsa no se
    propaga a toda la organización.
    """

    kind: ScopeKind
    carrier: str | None = None
    country: str | None = None
    zone: str | None = None
    site: str | None = None
    corridor: str | None = None
    client: str | None = None
    key: str = ""
    label: str = ""

    def to_public_dict(self) -> dict:
        return {
            "kind": self.kind,
            "carrier": self.carrier,
            "country": self.country,
            "zone": self.zone,
            "site": self.site,
            "corridor": self.corridor,
            "client": self.client,
            "key": self.key,
            "label": self.label,
        }


class MemoryProposalDraft(BaseModel):
    """Hecho que el agente propone recordar, ya validado en la ruta."""

    memory_type: MemoryType
    scope: MemoryScope
    fact: str = Field(min_length=1)
    reason: str | None = None
    source_quote: str = Field(min_length=1)


class MemoryProposalView(BaseModel):
    id: str
    memory_type: str
    scope: dict
    scope_label: str
    fact: str
    reason: str | None = None
    question: str
    created_at: str


class MemoryResolutionView(BaseModel):
    proposal_id: str
    decision: str
    status: str
    entry_id: str | None = None
    message: str


class MemoryEntryView(BaseModel):
    id: str
    memory_type: str
    scope_key: str
    scope_label: str
    fact: str
    status: str
    version: int
    created_at: str
    review_at: str | None = None


class GenerationOutcome(BaseModel):
    answer: str
    proposal: MemoryProposalDraft | None = None
    validation_error: str | None = None
    json_ok: bool = True


class EvaluationOutcome(BaseModel):
    proposal: MemoryProposalDraft | None = None
    validation_error: str | None = None
    json_ok: bool = True


class IntentDecision(BaseModel):
    decision: IntentLabel = "unrelated"
    confidence: float = 0.0
    edited_proposal: MemoryProposalDraft | None = None
    remaining_question: str | None = None
    reason: str | None = None


class IntentOutcome(BaseModel):
    decision: IntentDecision
    json_ok: bool = True
    error: str | None = None

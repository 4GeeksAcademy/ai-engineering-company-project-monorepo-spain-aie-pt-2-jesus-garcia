"""Generación y evaluación de propuestas por departamento (Hito 9, Parte 2).

La entrada es el handoff de enrutamiento de la Parte 1 (``ticket_id`` +
payload del synthesizer persistido en PostgreSQL). No se reparsea el PDF.
"""

from data.pipelines.rfp_intake.llm import JsonLlm, LlmClient

from .contract import (
    HandoffContractError,
    briefs_for_handoff,
    parse_intake_handoff,
    section_brief,
)
from .graph import build_proposal_graph
from .handoff import build_proposal_handoff
from .runner import ProposalPipelineError, run_proposal_generation

__all__ = [
    "HandoffContractError",
    "JsonLlm",
    "LlmClient",
    "ProposalPipelineError",
    "briefs_for_handoff",
    "build_proposal_graph",
    "build_proposal_handoff",
    "parse_intake_handoff",
    "run_proposal_generation",
    "section_brief",
]

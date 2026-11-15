"""Parte 3 del Hito 9: aprobación humana por departamento y cierre.

El paquete consume el handoff ``rfp-proposal-v1`` de la Parte 2, pausa cada
rama de departamento con ``interrupt`` y reanuda con ``Command(resume=...)``
sobre un checkpointer durable. No reejecuta la Parte 1 ni la propuesta
completa: los cambios solicitados por un humano se regeneran solo para la
sección afectada reutilizando el subgrafo generador-evaluador de la Parte 2.
"""

from .contracts import (
    APPROVAL_APPROVED,
    APPROVAL_CHANGES,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    FINAL_CONTRACT,
    PROPOSAL_CONTRACT,
    TICKET_AWAITING,
    TICKET_FINISHED,
    TICKET_NEEDS_REVIEW,
    ApprovalDecisionError,
    ApprovalError,
    ApprovalStateError,
)
from .runner import (
    approval_checkpoint_path,
    resume_approval,
    start_approval_flow,
)

__all__ = [
    "APPROVAL_APPROVED",
    "APPROVAL_CHANGES",
    "APPROVAL_PENDING",
    "APPROVAL_REJECTED",
    "FINAL_CONTRACT",
    "PROPOSAL_CONTRACT",
    "TICKET_AWAITING",
    "TICKET_FINISHED",
    "TICKET_NEEDS_REVIEW",
    "ApprovalDecisionError",
    "ApprovalError",
    "ApprovalStateError",
    "approval_checkpoint_path",
    "resume_approval",
    "start_approval_flow",
]

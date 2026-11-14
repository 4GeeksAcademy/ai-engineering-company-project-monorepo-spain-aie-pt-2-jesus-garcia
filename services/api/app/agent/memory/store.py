"""Interfaz explícita de lectura/escritura de la memoria del agente.

Ninguna función escribe en Qdrant ni en ``trackflow_knowledge``. El store es la
única puerta de entrada a ``agent_memory_*``: la lectura devuelve un bloque
acotado y la escritura solo ocurre tras una decisión explícita del usuario.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database import engine

from . import config
from .models import (
    AgentMemoryAudit,
    AgentMemoryEntry,
    AgentMemoryProposal,
)
from .scopes import scope_from_stored
from .schemas import (
    MemoryEntryView,
    MemoryProposalDraft,
    MemoryProposalView,
    MemoryResolutionView,
    MemoryScope,
)
from .validation import (
    contains_forbidden,
    message_hash,
    redact_text,
    validate_for_write,
    validate_proposal,
)

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "al", "algo", "como", "con", "cual", "cuales", "de", "del", "desde",
    "donde", "el", "ella", "en", "entre", "es", "esa", "ese", "eso", "esta",
    "este", "esto", "fue", "ha", "hace", "hay", "la", "las", "le", "lo",
    "los", "mas", "más", "me", "mi", "no", "nos", "o", "para", "pero", "por",
    "que", "qué", "se", "si", "sí", "sin", "son", "su", "sus", "tiene", "un",
    "una", "uno", "y", "ya", "esos", "esas", "este", "esta", "the", "of",
    "and", "to", "in", "is", "are", "for", "with", "on", "at",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class MemoryUnavailable(RuntimeError):
    """No hay engine SQL configurado para la memoria."""


@dataclass
class CreateProposalResult:
    created: bool
    proposal: AgentMemoryProposal | None = None
    reason: str | None = None
    validation_code: str | None = None


@dataclass
class ResolveResult:
    ok: bool
    status: str
    message: str
    proposal: AgentMemoryProposal | None = None
    entry: AgentMemoryEntry | None = None


@contextmanager
def memory_session():
    """Sesión de memoria; ``None`` si la API corre sin ``DATABASE_URL``."""

    if engine is None:
        yield None
        return
    with Session(engine) as session:
        yield session


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_past(value: datetime | None, now: datetime) -> bool:
    normalized = _as_utc(value)
    return normalized is not None and normalized <= now


def _iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat(timespec="seconds") if normalized else None


def _tokens(text: str | None) -> set[str]:
    from .scopes import normalize_text

    normalized = normalize_text(text or "")
    return {
        token
        for token in _TOKEN_RE.findall(normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _review_and_expiry(
    memory_type: str, now: datetime
) -> tuple[datetime | None, datetime | None]:
    if memory_type == "operational_context":
        expires = now + timedelta(days=config.EPISODIC_TTL_DAYS)
        return expires, expires
    if memory_type == "carrier_rule":
        return None, now + timedelta(days=config.CARRIER_REVIEW_DAYS)
    return None, now + timedelta(days=config.CLIENT_REVIEW_DAYS)


def _audit(
    session: Session,
    *,
    action: str,
    actor_user_id: str | None = None,
    session_id: str | None = None,
    proposal_id: str | None = None,
    entry_id: str | None = None,
    origin_message: str | None = None,
    detail: dict | None = None,
) -> None:
    redacted = redact_text(
        origin_message, limit=config.MAX_ORIGIN_MESSAGE_CHARS
    )
    session.add(
        AgentMemoryAudit(
            actor_user_id=actor_user_id,
            session_id=session_id,
            action=action,
            proposal_id=proposal_id,
            entry_id=entry_id,
            origin_message=redacted or None,
            origin_message_hash=(
                message_hash(origin_message) if origin_message else None
            ),
            detail=detail or {},
        )
    )


def _consolidate_after_write(session: Session) -> None:
    """La limpieza es best-effort: nunca debe tumbar una escritura ya hecha."""

    try:
        consolidate(session)
    except Exception:  # noqa: BLE001 - la escritura ya está confirmada
        logger.exception("Fallo al consolidar memoria tras una escritura")
        session.rollback()


def _apply_scope(proposal: AgentMemoryProposal, scope: MemoryScope) -> None:
    proposal.scope_type = scope.kind
    proposal.scope_key = scope.key
    proposal.scope_label = scope.label
    proposal.scope_json = scope.to_public_dict()


def _scope_of(proposal: AgentMemoryProposal) -> MemoryScope:
    return scope_from_stored(
        scope_type=proposal.scope_type,
        scope_key=proposal.scope_key,
        scope_label=proposal.scope_label,
        scope_json=proposal.scope_json,
    )


def draft_from_proposal(proposal: AgentMemoryProposal) -> MemoryProposalDraft:
    return MemoryProposalDraft(
        memory_type=proposal.memory_type,
        scope=_scope_of(proposal),
        fact=proposal.fact,
        reason=proposal.reason,
        source_quote=proposal.source_quote,
    )


def get_pending(
    session: Session,
    user_id: str,
    *,
    auto_expire: bool = True,
) -> AgentMemoryProposal | None:
    proposal = session.exec(
        select(AgentMemoryProposal)
        .where(
            AgentMemoryProposal.user_id == user_id,
            AgentMemoryProposal.status == "pending",
        )
        .order_by(AgentMemoryProposal.created_at.desc())
    ).first()
    if proposal is None:
        return None
    now = config.utcnow()
    if auto_expire and _is_past(proposal.expires_at, now):
        proposal.status = "rejected"
        proposal.decision_label = "unrelated"
        proposal.decision_message = (
            "Sin respuesta del usuario; rechazo por defecto."
        )
        proposal.decision_at = now
        _audit(
            session,
            action="rejected",
            actor_user_id=user_id,
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            detail={
                "reason": "proposal_ttl",
                "default_reject": True,
            },
        )
        session.commit()
        return None
    return proposal


def create_proposal(
    session: Session | None,
    *,
    session_id: str,
    user_id: str,
    run_id: str | None,
    draft: MemoryProposalDraft,
    origin_message: str,
) -> CreateProposalResult:
    if session is None:
        return CreateProposalResult(created=False, reason="memory_unavailable")
    if not config.ENABLED:
        return CreateProposalResult(created=False, reason="memory_disabled")

    issue = validate_proposal(draft, origin_message)
    if not issue.ok:
        _audit(
            session,
            action="blocked",
            actor_user_id=user_id,
            session_id=session_id,
            origin_message=origin_message,
            detail={
                "validation_code": issue.code,
                "validation_detail": issue.detail,
            },
        )
        session.commit()
        return CreateProposalResult(
            created=False,
            reason="validation_failed",
            validation_code=issue.code,
        )

    existing = get_pending(session, user_id, auto_expire=True)
    if existing is not None:
        _audit(
            session,
            action="proposal_skipped",
            actor_user_id=user_id,
            session_id=session_id,
            proposal_id=existing.id,
            origin_message=origin_message,
            detail={"reason": "already_pending"},
        )
        session.commit()
        return CreateProposalResult(created=False, reason="already_pending")

    now = config.utcnow()
    proposal = AgentMemoryProposal(
        session_id=session_id,
        user_id=user_id,
        run_id=run_id,
        memory_type=draft.memory_type,
        fact=draft.fact.strip(),
        reason=(draft.reason or "").strip() or None,
        source_quote=draft.source_quote.strip(),
        status="pending",
        expires_at=now + timedelta(hours=config.PROPOSAL_TTL_HOURS),
    )
    _apply_scope(proposal, draft.scope)
    session.add(proposal)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        _audit(
            session,
            action="proposal_skipped",
            actor_user_id=user_id,
            session_id=session_id,
            origin_message=origin_message,
            detail={"reason": "pending_race"},
        )
        session.commit()
        return CreateProposalResult(created=False, reason="already_pending")

    session.refresh(proposal)
    _audit(
        session,
        action="proposed",
        actor_user_id=user_id,
        session_id=session_id,
        proposal_id=proposal.id,
        origin_message=origin_message,
        detail={
            "memory_type": proposal.memory_type,
            "scope_key": proposal.scope_key,
        },
    )
    session.commit()
    _consolidate_after_write(session)
    return CreateProposalResult(created=True, proposal=proposal)


def _resolve_reject(
    session: Session,
    proposal: AgentMemoryProposal,
    *,
    user_id: str,
    decision: str,
    decision_message: str,
    confidence: float,
) -> ResolveResult:
    proposal.status = "rejected"
    proposal.decision_label = decision
    proposal.decision_confidence = confidence
    proposal.decision_message = redact_text(
        decision_message, limit=config.MAX_ORIGIN_MESSAGE_CHARS
    )
    proposal.decision_at = config.utcnow()
    _audit(
        session,
        action="rejected",
        actor_user_id=user_id,
        session_id=proposal.session_id,
        proposal_id=proposal.id,
        origin_message=decision_message,
        detail={
            "decision": decision,
            "confidence": confidence,
            "default_reject": decision == "unrelated",
        },
    )
    session.commit()
    _consolidate_after_write(session)
    return ResolveResult(
        ok=True,
        status="rejected",
        message="Entendido. No guardaré esa información.",
        proposal=proposal,
    )


def resolve_proposal(
    session: Session | None,
    proposal_id: str,
    *,
    user_id: str,
    user_role: str,
    decision: str,
    decision_message: str,
    edited_draft: MemoryProposalDraft | None = None,
    confidence: float = 0.0,
    allow_other_user: bool = False,
) -> ResolveResult:
    if session is None:
        return ResolveResult(
            ok=False,
            status="memory_unavailable",
            message="La memoria no está disponible.",
        )
    proposal = session.get(AgentMemoryProposal, proposal_id)
    if proposal is None:
        return ResolveResult(
            ok=False, status="not_found", message="La propuesta no existe."
        )
    if proposal.user_id != user_id and not allow_other_user:
        return ResolveResult(
            ok=False,
            status="forbidden",
            message="Esta propuesta no pertenece a tu usuario.",
        )
    if proposal.status != "pending":
        return ResolveResult(
            ok=False,
            status="not_pending",
            message="La propuesta ya está resuelta.",
        )

    normalized = (decision or "unrelated").lower()
    if normalized in {"reject", "unrelated"}:
        return _resolve_reject(
            session,
            proposal,
            user_id=user_id,
            decision=normalized,
            decision_message=decision_message,
            confidence=confidence,
        )

    if normalized not in {"approve", "edit"}:
        normalized = "unrelated"
        return _resolve_reject(
            session,
            proposal,
            user_id=user_id,
            decision=normalized,
            decision_message=decision_message,
            confidence=confidence,
        )

    final_draft = draft_from_proposal(proposal)
    if normalized == "edit":
        if edited_draft is None:
            proposal.status = "rejected"
            proposal.decision_label = "edit"
            proposal.decision_confidence = confidence
            proposal.decision_message = redact_text(decision_message)
            proposal.decision_at = config.utcnow()
            proposal.validation_code = "missing_edited_proposal"
            _audit(
                session,
                action="rejected",
                actor_user_id=user_id,
                session_id=proposal.session_id,
                proposal_id=proposal.id,
                origin_message=decision_message,
                detail={"reason": "missing_edited_proposal"},
            )
            session.commit()
            return ResolveResult(
                ok=False,
                status="rejected",
                message="No pude aplicar la edición. No se guardó nada.",
                proposal=proposal,
            )
        issue = validate_proposal(edited_draft, decision_message)
        if not issue.ok:
            proposal.status = "rejected"
            proposal.decision_label = "edit"
            proposal.decision_confidence = confidence
            proposal.decision_message = redact_text(decision_message)
            proposal.decision_at = config.utcnow()
            proposal.validation_code = issue.code
            proposal.validation_detail = issue.detail
            _audit(
                session,
                action="rejected",
                actor_user_id=user_id,
                session_id=proposal.session_id,
                proposal_id=proposal.id,
                origin_message=decision_message,
                detail={
                    "reason": "invalid_edit",
                    "validation_code": issue.code,
                },
            )
            session.commit()
            return ResolveResult(
                ok=False,
                status="rejected",
                message="La edición no cumple las reglas. No se guardó nada.",
                proposal=proposal,
            )
        final_draft = edited_draft

    issue = validate_for_write(final_draft, original_message=None)
    if not issue.ok:
        proposal.status = "blocked"
        proposal.validation_code = issue.code
        proposal.validation_detail = issue.detail
        _audit(
            session,
            action="blocked",
            actor_user_id=user_id,
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            origin_message=decision_message,
            detail={"validation_code": issue.code, "phase": "write"},
        )
        session.commit()
        return ResolveResult(
            ok=False,
            status="blocked",
            message="Esa información no puede guardarse.",
            proposal=proposal,
        )

    if (
        config.POLICY_APPROVER_ROLES
        and final_draft.memory_type in config.POLICY_MEMORY_TYPES
        and user_role.lower() not in config.POLICY_APPROVER_ROLES
    ):
        _audit(
            session,
            action="approval_deferred_role",
            actor_user_id=user_id,
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            origin_message=decision_message,
            detail={
                "memory_type": final_draft.memory_type,
                "user_role": user_role,
                "allowed_roles": sorted(config.POLICY_APPROVER_ROLES),
            },
        )
        session.commit()
        return ResolveResult(
            ok=False,
            status="awaiting_role",
            message=(
                "He registrado tu confirmación; una persona responsable debe "
                "validar esta regla antes de que el asistente la use."
            ),
            proposal=proposal,
        )

    now = config.utcnow()
    expires_at, review_at = _review_and_expiry(final_draft.memory_type, now)
    entry = _write_entry(
        session,
        draft=final_draft,
        proposal=proposal,
        user_id=user_id,
        now=now,
        expires_at=expires_at,
        review_at=review_at,
    )
    proposal.status = "edited" if normalized == "edit" else "approved"
    proposal.decision_label = normalized
    proposal.decision_confidence = confidence
    proposal.decision_message = redact_text(
        decision_message, limit=config.MAX_ORIGIN_MESSAGE_CHARS
    )
    proposal.decision_at = now
    proposal.resulting_entry_id = entry.id
    _audit(
        session,
        action=proposal.status,
        actor_user_id=user_id,
        session_id=proposal.session_id,
        proposal_id=proposal.id,
        entry_id=entry.id,
        origin_message=decision_message,
        detail={
            "decision": normalized,
            "memory_type": entry.memory_type,
            "scope_key": entry.scope_key,
            "version": entry.version,
        },
    )
    session.commit()
    _consolidate_after_write(session)
    return ResolveResult(
        ok=True,
        status=proposal.status,
        message="Hecho. Lo recordaré en futuras conversaciones.",
        proposal=proposal,
        entry=entry,
    )


def _write_entry(
    session: Session,
    *,
    draft: MemoryProposalDraft,
    proposal: AgentMemoryProposal,
    user_id: str,
    now: datetime,
    expires_at: datetime | None,
    review_at: datetime | None,
) -> AgentMemoryEntry:
    for attempt in range(2):
        previous = session.exec(
            select(AgentMemoryEntry)
            .where(
                AgentMemoryEntry.scope_key == draft.scope.key,
                AgentMemoryEntry.status == "active",
            )
            .order_by(AgentMemoryEntry.version.desc())
        ).first()
        if previous is not None:
            previous.status = "superseded"
            previous.updated_at = now
            session.add(previous)
            # El índice único parcial exige que la anterior deje de estar
            # activa antes de insertar la nueva versión.
            session.flush()

        entry = AgentMemoryEntry(
            memory_type=draft.memory_type,
            scope_type=draft.scope.kind,
            scope_key=draft.scope.key,
            scope_label=draft.scope.label,
            scope_json=draft.scope.to_public_dict(),
            fact=draft.fact.strip(),
            reason=(draft.reason or "").strip() or None,
            status="active",
            version=(previous.version + 1) if previous else 1,
            supersedes_id=previous.id if previous else None,
            source_proposal_id=proposal.id,
            created_by=proposal.user_id,
            approved_by=user_id,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            review_at=review_at,
        )
        session.add(entry)
        try:
            session.flush()
            return entry
        except IntegrityError:
            session.rollback()
            if attempt == 1:
                raise
            # Otra entrada activa ganó la carrera; se reintenta supersederla.
    raise RuntimeError("No se pudo escribir la entrada de memoria.")


def read_memory(
    session: Session | None,
    question: str,
    *,
    limit: int | None = None,
    max_chars: int | None = None,
) -> list[dict]:
    """Devuelve un bloque acotado y relevante de memoria activa.

    La relevancia se calcula con solapamiento de tokens (no hay VectorDB): el
    volumen es pequeño y estructurado, y así la lectura es determinista y
    auditable. Nunca se devuelven entradas caducadas, obsoletas ni bloqueadas.
    """

    if session is None:
        return []
    now = config.utcnow()
    entries = session.exec(
        select(AgentMemoryEntry).where(AgentMemoryEntry.status == "active")
    ).all()
    question_tokens = _tokens(question)
    if not question_tokens:
        return []

    scored: list[tuple[float, AgentMemoryEntry]] = []
    for entry in entries:
        if _is_past(entry.expires_at, now) or _is_past(entry.review_at, now):
            continue
        if contains_forbidden(entry.fact, memory_type=entry.memory_type):
            continue
        fact_tokens = _tokens(entry.fact) | _tokens(entry.scope_label)
        overlap = question_tokens & fact_tokens
        if not overlap:
            continue
        score = len(overlap) / max(1, len(fact_tokens)) ** 0.5
        if entry.memory_type == "operational_context":
            score += 0.05
        scored.append((score, entry))

    scored.sort(
        key=lambda item: (
            -item[0],
            -(_as_utc(item[1].updated_at) or now).timestamp(),
        )
    )
    max_entries = limit or config.MAX_CONTEXT_ENTRIES
    max_length = max_chars or config.MAX_CONTEXT_CHARS
    result: list[dict] = []
    used_chars = 0
    for _, entry in scored:
        payload = {
            "id": entry.id,
            "memory_type": entry.memory_type,
            "scope_type": entry.scope_type,
            "scope_key": entry.scope_key,
            "scope_label": entry.scope_label,
            "fact": entry.fact,
            "created_at": (_iso(entry.created_at) or "")[:10],
            "review_at": (_iso(entry.review_at) or "")[:10] or None,
        }
        size = len(payload["fact"]) + len(payload["scope_label"]) + 20
        if result and used_chars + size > max_length:
            break
        result.append(payload)
        used_chars += size
        if len(result) >= max_entries:
            break
    return result


def expire_stale_proposals(
    session: Session | None, *, now: datetime | None = None
) -> int:
    """Rechaza por defecto las propuestas pendientes vencidas (silencio)."""

    if session is None:
        return 0
    now = now or config.utcnow()
    pending = session.exec(
        select(AgentMemoryProposal).where(AgentMemoryProposal.status == "pending")
    ).all()
    count = 0
    for proposal in pending:
        if not _is_past(proposal.expires_at, now):
            continue
        proposal.status = "rejected"
        proposal.decision_label = "unrelated"
        proposal.decision_message = (
            "Sin respuesta del usuario; rechazo por defecto."
        )
        proposal.decision_at = now
        _audit(
            session,
            action="rejected",
            actor_user_id=proposal.user_id,
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            detail={
                "reason": "proposal_ttl",
                "default_reject": True,
            },
        )
        count += 1
    if count:
        session.commit()
    return count


def consolidate(
    session: Session | None, *, now: datetime | None = None
) -> dict[str, int]:
    """Política de limpieza: caducidad, obsolescencia, dedupe y tope."""

    if session is None:
        return {}
    now = now or config.utcnow()
    counts = {
        "rejected_stale_proposals": expire_stale_proposals(session, now=now),
        "expired_entries": 0,
        "stale_entries": 0,
        "superseded_duplicates": 0,
        "blocked_legacy": 0,
        "evicted": 0,
    }

    entries = session.exec(
        select(AgentMemoryEntry).where(AgentMemoryEntry.status == "active")
    ).all()

    for entry in entries:
        forbidden = contains_forbidden(
            entry.fact, memory_type=entry.memory_type
        )
        if forbidden:
            entry.status = "blocked"
            entry.updated_at = now
            counts["blocked_legacy"] += 1
            _audit(
                session,
                action="blocked_legacy",
                entry_id=entry.id,
                detail={"validation_code": forbidden},
            )
            continue
        if _is_past(entry.expires_at, now):
            entry.status = "expired"
            entry.updated_at = now
            counts["expired_entries"] += 1
            _audit(
                session,
                action="expired",
                entry_id=entry.id,
                detail={"reason": "entry_ttl"},
            )
            continue
        if _is_past(entry.review_at, now):
            entry.status = "stale"
            entry.updated_at = now
            counts["stale_entries"] += 1
            _audit(
                session,
                action="stale",
                entry_id=entry.id,
                detail={"reason": "review_due"},
            )

    session.commit()

    remaining = session.exec(
        select(AgentMemoryEntry).where(AgentMemoryEntry.status == "active")
    ).all()
    by_scope: dict[str, list[AgentMemoryEntry]] = {}
    for entry in remaining:
        by_scope.setdefault(entry.scope_key, []).append(entry)
    for scope_entries in by_scope.values():
        if len(scope_entries) <= 1:
            continue
        scope_entries.sort(
            key=lambda item: _as_utc(item.updated_at) or now,
            reverse=True,
        )
        for duplicate in scope_entries[1:]:
            duplicate.status = "superseded"
            duplicate.updated_at = now
            counts["superseded_duplicates"] += 1
            _audit(
                session,
                action="superseded_duplicate",
                entry_id=duplicate.id,
                detail={"scope_key": duplicate.scope_key},
            )
    session.commit()

    active = session.exec(
        select(AgentMemoryEntry).where(AgentMemoryEntry.status == "active")
    ).all()
    if len(active) > config.MAX_ACTIVE_ENTRIES:
        active.sort(
            key=lambda item: (
                0 if item.memory_type == "operational_context" else 1,
                _as_utc(item.updated_at) or now,
            )
        )
        for entry in active[: len(active) - config.MAX_ACTIVE_ENTRIES]:
            entry.status = "retired"
            entry.updated_at = now
            counts["evicted"] += 1
            _audit(
                session,
                action="evicted",
                entry_id=entry.id,
                detail={"reason": "active_cap"},
            )
        session.commit()

    if any(counts.values()):
        _audit(session, action="consolidated", detail=counts)
        session.commit()
    return counts


def list_entries(
    session: Session | None, *, include_inactive: bool = False
) -> list[MemoryEntryView]:
    if session is None:
        return []
    query = select(AgentMemoryEntry)
    if not include_inactive:
        query = query.where(AgentMemoryEntry.status == "active")
    entries = session.exec(
        query.order_by(AgentMemoryEntry.updated_at.desc())
    ).all()
    return [
        MemoryEntryView(
            id=entry.id,
            memory_type=entry.memory_type,
            scope_key=entry.scope_key,
            scope_label=entry.scope_label,
            fact=entry.fact,
            status=entry.status,
            version=entry.version,
            created_at=_iso(entry.created_at) or "",
            review_at=_iso(entry.review_at),
        )
        for entry in entries
    ]


def list_proposals(
    session: Session | None, *, status: str | None = None, limit: int = 100
) -> list[dict]:
    if session is None:
        return []
    query = select(AgentMemoryProposal)
    if status:
        query = query.where(AgentMemoryProposal.status == status)
    proposals = session.exec(
        query.order_by(AgentMemoryProposal.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "user_id": item.user_id,
            "run_id": item.run_id,
            "memory_type": item.memory_type,
            "scope": item.scope_json,
            "scope_label": item.scope_label,
            "fact": item.fact,
            "reason": item.reason,
            "status": item.status,
            "decision_label": item.decision_label,
            "decision_confidence": item.decision_confidence,
            "decision_message": item.decision_message,
            "decision_at": _iso(item.decision_at),
            "resulting_entry_id": item.resulting_entry_id,
            "validation_code": item.validation_code,
            "created_at": _iso(item.created_at),
        }
        for item in proposals
    ]


def retire_entry(
    session: Session | None,
    entry_id: str,
    *,
    actor_user_id: str,
    reason: str = "",
) -> bool:
    if session is None:
        return False
    entry = session.get(AgentMemoryEntry, entry_id)
    if entry is None or entry.status != "active":
        return False
    entry.status = "retired"
    entry.updated_at = config.utcnow()
    _audit(
        session,
        action="retired",
        actor_user_id=actor_user_id,
        entry_id=entry.id,
        detail={"reason": reason[:300]},
    )
    session.commit()
    return True


def chat_proposal_payload(proposal: AgentMemoryProposal) -> dict:
    """Propuesta serializada para el prompt del clasificador de intención."""

    return {
        "tipo": proposal.memory_type,
        "alcance": proposal.scope_json or {},
        "hecho": proposal.fact,
        "motivo": proposal.reason,
        "cita_origen": proposal.source_quote,
    }


def proposal_view(proposal: AgentMemoryProposal) -> MemoryProposalView:
    return MemoryProposalView(
        id=proposal.id,
        memory_type=proposal.memory_type,
        scope=proposal.scope_json or {},
        scope_label=proposal.scope_label,
        fact=proposal.fact,
        reason=proposal.reason,
        question=config.MEMORY_QUESTION,
        created_at=_iso(proposal.created_at) or "",
    )


def resolution_view(
    result: ResolveResult, *, proposal_id: str
) -> MemoryResolutionView:
    return MemoryResolutionView(
        proposal_id=proposal_id,
        decision=(
            result.proposal.decision_label
            if result.proposal and result.proposal.decision_label
            else "unrelated"
        ),
        status=result.status,
        entry_id=result.entry.id if result.entry else None,
        message=result.message,
    )


__all__ = [
    "CreateProposalResult",
    "MemoryUnavailable",
    "ResolveResult",
    "consolidate",
    "create_proposal",
    "chat_proposal_payload",
    "draft_from_proposal",
    "expire_stale_proposals",
    "get_pending",
    "list_entries",
    "list_proposals",
    "memory_session",
    "proposal_view",
    "read_memory",
    "resolution_view",
    "resolve_proposal",
    "retire_entry",
]

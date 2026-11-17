"""Persistencia de ``ChatSession`` y ``ChatMessage``.

Ninguna otra capa abre sesiones SQL para el chat. El store devuelve vistas
seguras (sin ORM expirado) para que la ruta y el WebSocket no compartan estado
mutable entre hilos.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import update
from sqlmodel import Session, select

from database import engine

from .config import AGENT_ID, HISTORY_LIMIT, MESSAGE_PREFIX, SESSION_PREFIX
from .models import ChatMessageRecord, ChatSessionRecord
from .schemas import ChatMessageView, ChatSessionView

logger = logging.getLogger(__name__)


class ChatUnavailable(RuntimeError):
    """No hay engine SQL configurado para el chat."""


@contextmanager
def chat_session():
    """Sesión SQL; ``None`` si la API corre sin ``DATABASE_URL``."""

    if engine is None:
        raise ChatUnavailable("DATABASE_URL no está configurada.")
    with Session(engine) as session:
        yield session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def new_session_id() -> str:
    return f"{SESSION_PREFIX}{uuid.uuid4().hex[:10]}"


def new_message_id() -> str:
    return f"{MESSAGE_PREFIX}{uuid.uuid4().hex[:10]}"


def _session_view(record: ChatSessionRecord) -> ChatSessionView:
    return ChatSessionView(
        session_id=record.session_id,
        thread_id=record.session_id,
        agent_id=record.agent_id or AGENT_ID,
        user_id=record.user_id,
        client_id=record.client_id,
        status=record.status,
        created_at=_iso(record.created_at),
    )


def _message_view(record: ChatMessageRecord) -> ChatMessageView:
    return ChatMessageView(
        message_id=record.message_id,
        session_id=record.session_id,
        role=record.role,
        text=record.text or "",
        status=record.status,
        sequence=int(record.sequence or 0),
        run_id=record.run_id,
        created_at=_iso(record.created_at),
    )


def create_session(*, user_id: str, client_id: str | None = None) -> ChatSessionView:
    now = _utcnow()
    record = ChatSessionRecord(
        session_id=new_session_id(),
        agent_id=AGENT_ID,
        user_id=user_id,
        client_id=client_id or None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    with chat_session() as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return _session_view(record)


def get_session(session_id: str) -> ChatSessionView | None:
    if not session_id:
        return None
    with chat_session() as session:
        record = session.get(ChatSessionRecord, session_id)
        return _session_view(record) if record is not None else None


def set_session_status(session_id: str, status: str) -> None:
    with chat_session() as session:
        record = session.get(ChatSessionRecord, session_id)
        if record is None:
            return
        record.status = status
        record.updated_at = _utcnow()
        session.add(record)
        session.commit()


def create_message(
    *,
    session_id: str,
    role: str,
    text: str = "",
    status: str = "streaming",
    run_id: str | None = None,
) -> ChatMessageView:
    now = _utcnow()
    record = ChatMessageRecord(
        message_id=new_message_id(),
        session_id=session_id,
        role=role,
        text=text,
        status=status,
        sequence=0,
        run_id=run_id,
        created_at=now,
        updated_at=now,
    )
    with chat_session() as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return _message_view(record)


def update_streaming_text(
    message_id: str,
    *,
    text: str,
    sequence: int,
) -> None:
    """Persiste un parcial sin tocar mensajes ya finalizados."""

    with chat_session() as session:
        session.execute(
            update(ChatMessageRecord)
            .where(ChatMessageRecord.message_id == message_id)
            .where(ChatMessageRecord.status == "streaming")
            .values(text=text, sequence=sequence, updated_at=_utcnow())
        )
        session.commit()


def finalize_message(
    message_id: str,
    *,
    text: str,
    sequence: int,
    status: str,
    run_id: str | None = None,
) -> None:
    if status not in ("completed", "interrupted", "failed"):
        raise ValueError(f"Estado final no válido: {status}")
    with chat_session() as session:
        record = session.get(ChatMessageRecord, message_id)
        if record is None:
            return
        if record.status != "streaming":
            # Un mensaje finalizado (interrumpido o completado) es inmutable.
            return
        record.text = text
        record.sequence = sequence
        record.status = status
        if run_id is not None:
            record.run_id = run_id
        record.updated_at = _utcnow()
        session.add(record)
        session.commit()


def list_messages(session_id: str, *, limit: int | None = None) -> list[ChatMessageView]:
    size = max(1, int(limit or HISTORY_LIMIT))
    with chat_session() as session:
        rows = session.exec(
            select(ChatMessageRecord)
            .where(ChatMessageRecord.session_id == session_id)
            .order_by(ChatMessageRecord.created_at.desc(), ChatMessageRecord.message_id.desc())
            .limit(size)
        ).all()
        return [_message_view(row) for row in reversed(rows)]


def dialog_history(session_id: str, *, limit: int) -> list[dict]:
    """Últimos turnos completados o interrumpidos, en orden cronológico."""

    messages = list_messages(session_id, limit=max(1, limit))
    history: list[dict] = []
    for message in messages:
        if message.status == "streaming":
            continue
        if not message.text.strip():
            continue
        history.append({"role": message.role, "text": message.text})
    return history


def reconcile_streaming_messages() -> int:
    """Marca como ``interrupted`` cualquier parcial huérfano de un reinicio."""

    with chat_session() as session:
        result = session.execute(
            update(ChatMessageRecord)
            .where(ChatMessageRecord.status == "streaming")
            .values(status="interrupted", updated_at=_utcnow())
        )
        session.commit()
        return int(result.rowcount or 0)


def session_belongs_to(session_id: str, user_id: str) -> bool:
    view = get_session(session_id)
    return bool(view is not None and str(view.user_id) == str(user_id))


__all__ = [
    "ChatUnavailable",
    "chat_session",
    "create_message",
    "create_session",
    "dialog_history",
    "finalize_message",
    "get_session",
    "list_messages",
    "new_message_id",
    "new_session_id",
    "reconcile_streaming_messages",
    "session_belongs_to",
    "set_session_status",
    "update_streaming_text",
]

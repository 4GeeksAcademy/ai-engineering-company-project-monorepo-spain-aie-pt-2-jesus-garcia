"""Store del chat: sesiones, mensajes, parciales y rehidratación."""

from __future__ import annotations

from app.chat import store
from app.chat.service import ChatService


def test_create_session_binds_agent_and_owner() -> None:
    session = store.create_session(user_id="user-1", client_id="client-9")
    assert session.session_id.startswith("chat_")
    assert session.thread_id == session.session_id
    assert session.agent_id == "first_line_cx"
    assert session.user_id == "user-1"
    assert session.client_id == "client-9"
    assert session.status == "active"
    assert store.session_belongs_to(session.session_id, "user-1")
    assert not store.session_belongs_to(session.session_id, "user-2")


def test_messages_are_ordered_and_snapshot_limited() -> None:
    session = store.create_session(user_id="user-1")
    first = store.create_message(
        session_id=session.session_id,
        role="user",
        text="hola",
        status="completed",
    )
    second = store.create_message(
        session_id=session.session_id,
        role="assistant",
        text="respuesta",
        status="completed",
    )
    messages = store.list_messages(session.session_id)
    assert [message.message_id for message in messages] == [
        first.message_id,
        second.message_id,
    ]


def test_partial_message_is_kept_as_interrupted_and_not_overwritten() -> None:
    session = store.create_session(user_id="user-1")
    assistant = store.create_message(
        session_id=session.session_id,
        role="assistant",
        status="streaming",
        run_id="run-1",
    )
    store.update_streaming_text(
        assistant.message_id,
        text="La entrega",
        sequence=3,
    )
    store.finalize_message(
        assistant.message_id,
        text="La entrega",
        sequence=3,
        status="interrupted",
        run_id="run-1",
    )
    # Un cierre tardío del productor no debe sobrescribir el parcial.
    store.finalize_message(
        assistant.message_id,
        text="texto completo que no llegó",
        sequence=99,
        status="completed",
    )
    stored = store.list_messages(session.session_id)[0]
    assert stored.status == "interrupted"
    assert stored.text == "La entrega"
    assert stored.sequence == 3


def test_dialog_history_excludes_streaming_and_empty() -> None:
    session = store.create_session(user_id="user-1")
    store.create_message(
        session_id=session.session_id,
        role="user",
        text="¿Dónde está mi pedido?",
        status="completed",
    )
    store.create_message(
        session_id=session.session_id,
        role="assistant",
        text="",
        status="streaming",
    )
    store.create_message(
        session_id=session.session_id,
        role="assistant",
        text="Está en reparto.",
        status="interrupted",
    )
    history = store.dialog_history(session.session_id, limit=10)
    assert history == [
        {"role": "user", "text": "¿Dónde está mi pedido?"},
        {"role": "assistant", "text": "Está en reparto."},
    ]


def test_reconcile_marks_orphan_streaming_as_interrupted() -> None:
    session = store.create_session(user_id="user-1")
    orphan = store.create_message(
        session_id=session.session_id,
        role="assistant",
        text="parcial",
        status="streaming",
    )
    assert store.reconcile_streaming_messages() >= 1
    stored = store.list_messages(session.session_id)[0]
    assert stored.message_id == orphan.message_id
    assert stored.status == "interrupted"


def test_supervisor_access_is_read_only() -> None:
    session = store.create_session(user_id="user-1")
    owner = {"id": "user-1", "role": "user"}
    supervisor = {"id": "manager-1", "role": "manager"}
    outsider = {"id": "user-2", "role": "user"}
    assert ChatService.can_access(session, owner)
    assert ChatService.can_access(session, supervisor)
    assert not ChatService.can_write(session, supervisor)
    assert not ChatService.can_access(session, outsider)

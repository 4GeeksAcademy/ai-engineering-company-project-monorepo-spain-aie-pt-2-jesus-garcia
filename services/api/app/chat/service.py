"""Orquestación del chat: productor de tokens, interrupción y rehidratación.

El servicio no habla WebSocket. Publica eventos en :class:`ChatEventBus` y el
endpoint se limita a traducir comandos y reenviar eventos. Así el productor y
los consumidores quedan desacoplados y varias conexiones de la misma sesión
comparten una única llamada al agente.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from typing import Any

from app.agent.memory.service import ChatResult, chat as agent_chat
from app.agent.streaming import GenerationAborted

from . import config, events, store
from .bus import ChatEventBus, get_chat_bus, reset_chat_bus
from .generations import ActiveGeneration, GenerationRegistry
from .schemas import (
    ActiveGenerationView,
    ChatSessionView,
    SessionSnapshotView,
)

logger = logging.getLogger(__name__)

SAFE_ERROR_TEXT = (
    "No se pudo completar la consulta en este momento. "
    "Inténtalo de nuevo en unos minutos."
)

AgentRunner = Callable[..., ChatResult]


def run_cx_turn(
    question: str,
    *,
    user: dict | None,
    session_id: str,
    conversation_history: list[dict],
    on_token: Callable[[str], None] | None,
    abort: Any | None,
) -> ChatResult:
    """Adaptador al agente real. El hilo persistente es la propia sesión."""

    return agent_chat(
        question,
        user=user,
        session_id=session_id,
        thread_id=session_id,
        token_sink=on_token,
        abort=abort,
        conversation_history=conversation_history,
    )


def _chunks(text: str, size: int = 14) -> list[str]:
    """Divide texto en trozos sin partir palabras, para rutas deterministas."""

    if not text:
        return []
    words = re.findall(r"\S+\s*|\s+", text)
    chunks: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) > size:
            chunks.append(current)
            current = word
        else:
            current += word
    if current:
        chunks.append(current)
    return chunks


class ChatService:
    """Una instancia por proceso; el estado activo vive en memoria."""

    def __init__(
        self,
        *,
        runner: AgentRunner | None = None,
        bus: ChatEventBus | None = None,
        registry: GenerationRegistry | None = None,
    ) -> None:
        self._runner = runner or run_cx_turn
        self.bus = bus or get_chat_bus()
        self.registry = registry or GenerationRegistry()
        self._turn_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ auth
    @staticmethod
    def can_access(session: ChatSessionView, user: dict) -> bool:
        user_id = str(user.get("id") or "")
        if session.user_id == user_id:
            return True
        return str(user.get("role") or "") in ("admin", "manager")

    @staticmethod
    def can_write(session: ChatSessionView, user: dict) -> bool:
        return session.user_id == str(user.get("id") or "")

    # --------------------------------------------------------------- sesiones
    def create_session(
        self,
        *,
        user: dict,
        client_id: str | None = None,
    ) -> ChatSessionView:
        return store.create_session(
            user_id=str(user.get("id") or ""),
            client_id=client_id,
        )

    def get_session(self, session_id: str) -> ChatSessionView | None:
        return store.get_session(session_id)

    def snapshot(self, session_id: str) -> SessionSnapshotView:
        session = store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        messages = store.list_messages(session_id)
        active = None
        generation = self.registry.get(session_id)
        if generation is not None:
            sequence, text = generation.snapshot()
            active = ActiveGenerationView(
                message_id=generation.message_id,
                run_id=generation.run_id,
                sequence=sequence,
                text=text,
            )
        return SessionSnapshotView(
            session_id=session.session_id,
            thread_id=session.thread_id,
            agent_id=session.agent_id,
            status="active" if generation is not None else session.status,
            messages=messages,
            active_generation=active,
        )

    # ----------------------------------------------------------------- eventos
    def _publish(self, session_id: str, name: str, data: dict[str, Any]) -> None:
        self.bus.publish(
            session_id,
            name,
            {"session_id": session_id, **data},
        )

    def publish_error(self, session_id: str, code: str, message: str) -> None:
        self._publish(
            session_id,
            events.ERROR,
            {"code": code, "message": message},
        )

    def _publish_token(
        self,
        generation: ActiveGeneration,
        sequence: int,
        chunk: str,
    ) -> None:
        self._publish(
            generation.session_id,
            events.TOKEN_CHUNK,
            {
                "message_id": generation.message_id,
                "run_id": generation.run_id,
                "token": chunk,
                "sequence": sequence,
            },
        )

    def _publish_interrupt(
        self,
        generation: ActiveGeneration,
        new_input: str | None,
    ) -> None:
        self._publish(
            generation.session_id,
            events.INTERRUPT_REQUESTED,
            {
                "message_id": generation.message_id,
                "new_input": new_input or "",
            },
        )

    def _close_generation(self, generation: ActiveGeneration, aborted: bool, sequence: int, text: str, meta: dict[str, Any]) -> None:
        """Callback de cierre: persiste y emite el evento terminal."""

        session_id = generation.session_id
        try:
            if aborted:
                store.finalize_message(
                    generation.message_id,
                    text=text,
                    sequence=sequence,
                    status="interrupted",
                    run_id=generation.run_id,
                )
                store.set_session_status(session_id, "interrupted")
                self._publish(
                    session_id,
                    events.GENERATION_INTERRUPTED,
                    {
                        "message_id": generation.message_id,
                        "run_id": generation.run_id,
                        "status": "interrupted",
                        "text": text,
                        "sequence": sequence,
                    },
                )
                return

            status = str(meta.get("status") or "completed")
            db_status = "failed" if status in ("error", "invalid_question") else "completed"
            store.finalize_message(
                generation.message_id,
                text=text,
                sequence=sequence,
                status=db_status,
                run_id=generation.run_id,
            )
            store.set_session_status(session_id, "active")
            self._publish(
                session_id,
                events.GENERATION_COMPLETED,
                {
                    "message_id": generation.message_id,
                    "run_id": generation.run_id,
                    "status": status,
                    "blocked": bool(meta.get("blocked")),
                    "text": text,
                },
            )
        except Exception:  # noqa: BLE001 - nunca dejamos un parcial sin cerrar
            logger.exception("No se pudo cerrar el mensaje %s", generation.message_id)
            self._publish(
                session_id,
                events.ERROR,
                {
                    "code": "persist_failed",
                    "message": "No se pudo guardar el mensaje del asistente.",
                },
            )

    # ------------------------------------------------------------------ turnos
    def _turn_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._turn_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._turn_locks[session_id] = lock
        return lock

    def _history(self, session_id: str) -> list[dict]:
        items = store.dialog_history(
            session_id,
            limit=config.PROMPT_HISTORY_MESSAGES,
        )
        total = 0
        selected: list[dict] = []
        for item in reversed(items):
            text = str(item.get("text") or "")
            if total + len(text) > config.PROMPT_HISTORY_CHARS and selected:
                break
            selected.append(item)
            total += len(text)
        return list(reversed(selected))

    def _invoke_runner(
        self,
        *,
        question: str,
        user: dict,
        session_id: str,
        history: list[dict],
        generation: ActiveGeneration,
    ) -> ChatResult:
        try:
            return self._runner(
                question,
                user=user,
                session_id=session_id,
                conversation_history=history,
                on_token=lambda chunk: self._on_token(generation, chunk),
                abort=generation.abort,
            )
        except GenerationAborted:
            return ChatResult(
                session_id=session_id,
                run_id=generation.run_id,
                answer="",
                status="interrupted",
            )
        except Exception:  # noqa: BLE001 - el detalle no sale al cliente
            logger.exception("Fallo inesperado del agente en el chat")
            return ChatResult(
                session_id=session_id,
                run_id=generation.run_id,
                answer="",
                status="error",
                error=SAFE_ERROR_TEXT,
            )

    def _on_token(self, generation: ActiveGeneration, chunk: str) -> None:
        sequence = generation.emit_token(chunk, self._publish_token)
        if sequence and sequence % config.PARTIAL_PERSIST_EVERY == 0:
            try:
                _, text = generation.snapshot()
                store.update_streaming_text(
                    generation.message_id,
                    text=text,
                    sequence=sequence,
                )
            except Exception:  # noqa: BLE001 - el parcial se guardará al cerrar
                logger.debug("No se pudo persistir el parcial todavía")

    async def _emit_text(self, generation: ActiveGeneration, text: str) -> None:
        for chunk in _chunks(text):
            if generation.is_aborted():
                return
            if generation.emit_token(chunk, self._publish_token) is None:
                return
            await asyncio.sleep(0.005)

    async def _complete(
        self,
        generation: ActiveGeneration,
        result: ChatResult,
    ) -> None:
        final_text = (result.answer or "").strip()
        if not final_text:
            final_text = (
                SAFE_ERROR_TEXT
                if result.status in ("error", "invalid_question")
                else generation.snapshot()[1]
            )

        _, streamed = generation.snapshot()
        blocked = False

        if not streamed:
            await self._emit_text(generation, final_text)
        elif final_text.startswith(streamed):
            await self._emit_text(generation, final_text[len(streamed):])
        elif streamed.startswith(final_text):
            # El guardrail recortó el final: se conserva lo ya mostrado.
            final_text = streamed
        elif result.status == "blocked":
            # Respuesta bloqueada por el output guard: la UI sustituye el
            # parcial por el mensaje seguro (única excepción a "no reemplazar").
            blocked = True
        else:
            logger.warning(
                "El texto final no coincide con el stream; se conserva el parcial "
                "message_id=%s",
                generation.message_id,
            )
            final_text = streamed

        generation.close(
            self._close_generation,
            completed_text=final_text,
            meta={"status": result.status, "blocked": blocked},
        )

    async def _run_generation(
        self,
        generation: ActiveGeneration,
        session: ChatSessionView,
        user: dict,
        question: str,
        history: list[dict],
    ) -> None:
        try:
            result = await asyncio.to_thread(
                self._invoke_runner,
                question=question,
                user=user,
                session_id=session.session_id,
                history=history,
                generation=generation,
            )
            if generation.is_aborted() or result.status == "interrupted":
                generation.close(self._close_generation, completed_text="")
            else:
                await self._complete(generation, result)
        finally:
            self.registry.release(generation)

    async def start_turn(
        self,
        session: ChatSessionView,
        user: dict,
        text: str,
    ) -> ActiveGeneration | None:
        lock = self._turn_lock(session.session_id)
        async with lock:
            if self.registry.get(session.session_id) is not None:
                self.publish_error(
                    session.session_id,
                    "generation_in_progress",
                    "Ya hay una respuesta en curso para esta sesión.",
                )
                return None

            message = (text or "").strip()
            if not message:
                self.publish_error(
                    session.session_id,
                    "empty_message",
                    "El mensaje no puede estar vacío.",
                )
                return None
            if len(message) > config.MAX_MESSAGE_CHARS:
                self.publish_error(
                    session.session_id,
                    "message_too_long",
                    "El mensaje supera el máximo permitido.",
                )
                return None

            history = self._history(session.session_id)
            user_message = store.create_message(
                session_id=session.session_id,
                role="user",
                text=message,
                status="completed",
            )
            self._publish(
                session.session_id,
                events.USER_MESSAGE,
                {
                    "message_id": user_message.message_id,
                    "text": user_message.text,
                },
            )

            run_id = str(uuid.uuid4())
            assistant = store.create_message(
                session_id=session.session_id,
                role="assistant",
                text="",
                status="streaming",
                run_id=run_id,
            )
            generation = ActiveGeneration(
                session_id=session.session_id,
                message_id=assistant.message_id,
                run_id=run_id,
                user_id=str(user.get("id") or ""),
            )
            if not self.registry.try_register(generation):
                store.finalize_message(
                    assistant.message_id,
                    text="",
                    sequence=0,
                    status="failed",
                    run_id=run_id,
                )
                self.publish_error(
                    session.session_id,
                    "generation_in_progress",
                    "Ya hay una respuesta en curso para esta sesión.",
                )
                return None

            store.set_session_status(session.session_id, "active")
            self._publish(
                session.session_id,
                events.GENERATION_STARTED,
                {
                    "message_id": assistant.message_id,
                    "run_id": run_id,
                },
            )
            generation.task = asyncio.create_task(
                self._run_generation(
                    generation,
                    session,
                    user,
                    message,
                    history,
                )
            )
            return generation

    async def _wait_generation(self, generation: ActiveGeneration) -> None:
        task = generation.task
        if task is None:
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=config.ABORT_WAIT_SECONDS,
            )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(
                "La generación %s no terminó tras el aborto; se cierra igualmente",
                generation.message_id,
            )
            generation.close(self._close_generation, completed_text="")
            self.registry.release(generation)
        except Exception:  # noqa: BLE001 - la tarea ya cierra su propio error
            logger.exception("Fallo esperando el cierre de la generación")

    async def interrupt(
        self,
        session: ChatSessionView,
        user: dict,
        new_input: str | None = None,
    ) -> bool:
        if not self.can_write(session, user):
            self.publish_error(
                session.session_id,
                "forbidden",
                "Solo el propietario de la sesión puede interrumpirla.",
            )
            return False

        generation = self.registry.get(session.session_id)
        if generation is None:
            self.publish_error(
                session.session_id,
                "no_active_generation",
                "No hay ninguna respuesta en curso para interrumpir.",
            )
            return False

        changed = generation.request_abort(self._publish_interrupt, new_input)
        if not changed:
            return False

        await self._wait_generation(generation)

        text = (new_input or "").strip()
        if text:
            await self.start_turn(session, user, text)
        return True

    async def handle_user_message(
        self,
        session: ChatSessionView,
        user: dict,
        text: str,
    ) -> None:
        if not self.can_write(session, user):
            self.publish_error(
                session.session_id,
                "forbidden",
                "Solo el propietario de la sesión puede escribir en el chat.",
            )
            return

        if self.registry.get(session.session_id) is None:
            await self.start_turn(session, user, text)
            return

        if not await self.interrupt(session, user, text):
            generation = self.registry.get(session.session_id)
            if generation is not None:
                await self._wait_generation(generation)
            await self.start_turn(session, user, text)


_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service


def set_chat_service(service: ChatService | None) -> None:
    global _service
    _service = service


def reset_chat_service() -> None:
    global _service
    _service = None
    reset_chat_bus()


__all__ = [
    "AgentRunner",
    "ChatService",
    "SAFE_ERROR_TEXT",
    "get_chat_service",
    "reset_chat_service",
    "run_cx_turn",
    "set_chat_service",
]

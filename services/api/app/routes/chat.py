"""Router del chat: sesiones REST y WebSocket de streaming.

El WebSocket exige el mismo JWT del backoffice (``?token=`` o primer frame
``auth``), se liga a una ``session_id`` existente y reenvía los eventos del
pub/sub. El productor (agente) no conoce sockets: solo publica en
``chat.<session_id>``.
"""

from __future__ import annotations

import asyncio
import logging

import anyio

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from starlette.concurrency import run_in_threadpool

from app.chat import config, store
from app.chat.bus import ChatSubscription
from app.chat.schemas import ChatMessageView, ChatSessionCreate, ChatSessionView
from app.chat.service import ChatService, get_chat_service
from app.core.dependencies import authenticate_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404
WS_BAD_REQUEST = 4400


# --------------------------------------------------------------------- REST
@router.post(
    "/sessions",
    response_model=ChatSessionView,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una sesión de chat con el First-line CX agent",
)
def create_chat_session(
    payload: ChatSessionCreate | None = None,
    current_user: dict = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionView:
    try:
        return service.create_session(
            user=current_user,
            client_id=payload.client_id if payload is not None else None,
        )
    except store.ChatUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El chat no está disponible sin base_de_datos.",
        ) from exc


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionView,
    summary="Consultar una sesión de chat existente",
)
def get_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionView:
    try:
        session = service.get_session(session_id)
    except store.ChatUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El chat no está disponible.",
        ) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="La sesión no existe.")
    if not service.can_access(session, current_user):
        raise HTTPException(status_code=403, detail="No tienes acceso a la sesión.")
    return session


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageView],
    summary="Historial persistido de una sesión (rehidratación REST)",
)
def get_chat_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> list[ChatMessageView]:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="La sesión no existe.")
    if not service.can_access(session, current_user):
        raise HTTPException(status_code=403, detail="No tienes acceso a la sesión.")
    return store.list_messages(session_id)


# ---------------------------------------------------------------- WebSocket
async def _authenticate_socket(
    websocket: WebSocket,
    token: str | None,
) -> dict | None:
    """Valida el JWT antes de cualquier evento de chat.

    Con ``?token=`` se rechaza el handshake directamente. Sin token se acepta y
    se espera un primer frame ``{"event": "auth", "data": {"token": ...}}``.
    """

    provided = (token or "").strip()
    if provided:
        try:
            user = await run_in_threadpool(authenticate_token, provided)
        except HTTPException:
            await websocket.close(code=WS_UNAUTHORIZED)
            return None
        await websocket.accept()
        return user

    await websocket.accept()
    try:
        frame = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=config.AUTH_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError, WebSocketDisconnect):
        await websocket.close(code=WS_UNAUTHORIZED)
        return None
    if not isinstance(frame, dict) or frame.get("event") != "auth":
        await websocket.close(code=WS_UNAUTHORIZED)
        return None
    data = frame.get("data") if isinstance(frame.get("data"), dict) else {}
    candidate = str((data or {}).get("token") or "").strip()
    if not candidate:
        await websocket.close(code=WS_UNAUTHORIZED)
        return None
    try:
        return await run_in_threadpool(authenticate_token, candidate)
    except HTTPException:
        await websocket.close(code=WS_UNAUTHORIZED)
        return None


async def _receive_loop(
    websocket: WebSocket,
    session: ChatSessionView,
    user: dict,
    service: ChatService,
) -> None:
    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001 - frame no JSON o socket roto
            return
        if not isinstance(payload, dict):
            continue
        event = str(payload.get("event") or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        data = data or {}

        event_session = str(data.get("session_id") or session.session_id)
        if event_session != session.session_id:
            service.publish_error(
                session.session_id,
                "session_mismatch",
                "El evento no pertenece a esta sesión.",
            )
            continue

        if event == "user_message":
            await service.handle_user_message(
                session,
                user,
                str(data.get("text") or ""),
            )
        elif event == "interrupt_requested":
            new_input = data.get("new_input")
            await service.interrupt(
                session,
                user,
                None if new_input is None else str(new_input),
            )
        elif event in ("pong", "ping"):
            continue
        else:
            service.publish_error(
                session.session_id,
                "unknown_event",
                f"Evento no soportado: {event or '<vacío>'}.",
            )


async def _pump_loop(
    websocket: WebSocket,
    session_id: str,
    subscription: ChatSubscription,
) -> None:
    while True:
        try:
            event = await asyncio.wait_for(
                subscription.get(),
                timeout=config.KEEPALIVE_SECONDS,
            )
        except (asyncio.TimeoutError, TimeoutError):
            await websocket.send_json(
                {"event": "ping", "data": {"session_id": session_id}}
            )
            continue
        except Exception:  # noqa: BLE001 - socket cerrado
            return
        try:
            await websocket.send_json(event.to_wire())
        except Exception:  # noqa: BLE001 - el cliente se fue
            return


@router.websocket("/ws")
async def chat_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    service: ChatService = Depends(get_chat_service),
) -> None:
    user = await _authenticate_socket(websocket, token)
    if user is None:
        return

    resolved = (session_id or thread_id or "").strip()
    if not resolved:
        await websocket.close(code=WS_BAD_REQUEST)
        return
    if session_id and thread_id and session_id != thread_id:
        await websocket.close(code=WS_BAD_REQUEST)
        return

    try:
        session = await run_in_threadpool(service.get_session, resolved)
    except store.ChatUnavailable:
        await websocket.close(code=WS_BAD_REQUEST)
        return
    if session is None:
        await websocket.close(code=WS_NOT_FOUND)
        return
    if not service.can_access(session, user):
        await websocket.close(code=WS_FORBIDDEN)
        return

    loop = asyncio.get_running_loop()
    subscription = await service.bus.subscribe(session.session_id, loop)
    try:
        snapshot = await run_in_threadpool(service.snapshot, session.session_id)
        await websocket.send_json(
            {
                "event": snapshot.event,
                "data": snapshot.model_dump(exclude={"event"}),
            }
        )

        async with anyio.create_task_group() as group:

            async def receive_task() -> None:
                try:
                    await _receive_loop(websocket, session, user, service)
                finally:
                    group.cancel_scope.cancel()

            async def pump_task() -> None:
                try:
                    await _pump_loop(websocket, session.session_id, subscription)
                finally:
                    group.cancel_scope.cancel()

            group.start_soon(receive_task)
            group.start_soon(pump_task)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - nunca dejamos suscripciones colgadas
        logger.exception("Fallo no controlado en el WebSocket del chat")
    finally:
        await service.bus.unsubscribe(session.session_id, subscription)


__all__ = ["router"]

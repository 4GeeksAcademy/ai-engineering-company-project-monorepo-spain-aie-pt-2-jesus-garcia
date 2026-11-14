"""Observabilidad mínima del harness: eventos, logs y contadores.

Cada bloqueo, redirección, corrección o saneamiento genera un
:class:`GuardrailEvent` con su **tipo de fallo**:

* ``structural`` — formato de entrada/salida inválido;
* ``content`` — fuera de dominio, uso personal, mezcla de políticas, dato
  sensible en la salida;
* ``security`` — inyección de instrucciones, pedido de otra sesión, contenido
  externo con órdenes, fuga del prompt.

El evento se registra en el log y en contadores en memoria. El endpoint
``GET /agent/harness/stats`` expone el resumen de la sesión de pruebas.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock

from ..memory.validation import redact_text

logger = logging.getLogger("trackflow.agent.harness")

CATEGORY_STRUCTURAL = "structural"
CATEGORY_CONTENT = "content"
CATEGORY_SECURITY = "security"

ACTION_BLOCKED = "blocked"
ACTION_REDIRECTED = "redirected"
ACTION_CORRECTED = "corrected"
ACTION_SANITIZED = "sanitized"

MAX_RECENT_EVENTS = 100
SNIPPET_CHARS = 160


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def question_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def safe_snippet(text: str | None, *, limit: int = SNIPPET_CHARS) -> str:
    """Fragmento redactado y truncado; nunca se loguea la pregunta completa."""

    cleaned = redact_text(str(text or ""))
    cleaned = re.sub(
        r"(?<!\w)#\s*\d{4,12}\b",
        "#[REDACTED_ORDER]",
        cleaned,
    )
    cleaned = re.sub(
        r"\b(pedido|order|tracking|env[ií]o|gu[ií]a)\s*[:#-]?\s*"
        r"[A-Za-z0-9][A-Za-z0-9-]{2,23}\b",
        r"\1 [REDACTED_ORDER]",
        cleaned,
        flags=re.IGNORECASE,
    )
    if len(cleaned) > limit:
        cleaned = cleaned[: max(0, limit - 1)].rstrip() + "…"
    return cleaned


@dataclass(frozen=True)
class GuardrailEvent:
    guard: str
    category: str
    action: str
    reason: str
    run_id: str | None = None
    session_id: str | None = None
    snippet: str = ""
    question_sha256: str | None = None
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, object]:
        return {
            "guard": self.guard,
            "category": self.category,
            "action": self.action,
            "reason": self.reason,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "snippet": self.snippet,
            "question_sha256": self.question_sha256,
            "timestamp": self.timestamp,
        }


class GuardrailMetrics:
    """Contadores thread-safe, globales y por sesión."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.since = _utc_now()
            self._totals: Counter[str] = Counter()
            self._by_category: Counter[str] = Counter()
            self._by_guard: Counter[str] = Counter()
            self._by_reason: Counter[str] = Counter()
            self._recent: deque[dict[str, object]] = deque(
                maxlen=MAX_RECENT_EVENTS
            )
            self._sessions: dict[str, dict[str, object]] = {}

    def _session(self, session_id: str) -> dict[str, object]:
        state = self._sessions.get(session_id)
        if state is None:
            state = {
                "since": _utc_now(),
                "totals": Counter(),
                "by_category": Counter(),
                "by_guard": Counter(),
                "by_reason": Counter(),
            }
            self._sessions[session_id] = state
        return state

    def record(self, event: GuardrailEvent) -> GuardrailEvent:
        payload = event.to_dict()
        with self._lock:
            targets = [
                (
                    self._totals,
                    self._by_category,
                    self._by_guard,
                    self._by_reason,
                )
            ]
            if event.session_id:
                session = self._session(event.session_id)
                targets.append(
                    (
                        session["totals"],  # type: ignore[arg-type]
                        session["by_category"],  # type: ignore[arg-type]
                        session["by_guard"],  # type: ignore[arg-type]
                        session["by_reason"],  # type: ignore[arg-type]
                    )
                )
            for totals, by_category, by_guard, by_reason in targets:
                totals[event.action] += 1
                by_category[event.category] += 1
                by_guard[event.guard] += 1
                by_reason[event.reason] += 1
            self._recent.append(payload)

        logger.warning(
            "guardrail_triggered %s",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        return event

    def snapshot(
        self,
        *,
        session_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, object]:
        with self._lock:
            if session_id:
                state = self._sessions.get(session_id)
                if state is None:
                    return {
                        "since": self.since,
                        "session_id": session_id,
                        "totals": {},
                        "by_category": {},
                        "by_guard": {},
                        "by_reason": {},
                        "recent": [],
                    }
                totals = dict(state["totals"])  # type: ignore[arg-type]
                by_category = dict(state["by_category"])  # type: ignore[arg-type]
                by_guard = dict(state["by_guard"])  # type: ignore[arg-type]
                by_reason = dict(state["by_reason"])  # type: ignore[arg-type]
                since = str(state["since"])
            else:
                totals = dict(self._totals)
                by_category = dict(self._by_category)
                by_guard = dict(self._by_guard)
                by_reason = dict(self._by_reason)
                since = self.since

            recent = [
                item
                for item in self._recent
                if not session_id or item.get("session_id") == session_id
            ][-limit:]
            return {
                "since": since,
                "session_id": session_id,
                "totals": totals,
                "by_category": by_category,
                "by_guard": by_guard,
                "by_reason": by_reason,
                "recent": list(reversed(recent)),
            }


metrics = GuardrailMetrics()


def reset_metrics() -> None:
    metrics.reset()


__all__ = [
    "ACTION_BLOCKED",
    "ACTION_CORRECTED",
    "ACTION_REDIRECTED",
    "ACTION_SANITIZED",
    "CATEGORY_CONTENT",
    "CATEGORY_SECURITY",
    "CATEGORY_STRUCTURAL",
    "GuardrailEvent",
    "GuardrailMetrics",
    "metrics",
    "question_hash",
    "reset_metrics",
    "safe_snippet",
]

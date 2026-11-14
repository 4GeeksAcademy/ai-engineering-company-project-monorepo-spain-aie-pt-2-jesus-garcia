"""Autorización por sesión para consultas de pedidos y tracking.

El briefing identifica un riesgo específico de TrackFlow: un usuario que
cambia el número de tracking para consultar el pedido de otra persona. El
guard no distingue entre "no existe" y "no es tuyo": en ambos casos rechaza
por falta de autorización para no filtrar la existencia de pedidos ajenos.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("trackflow.agent.harness.orders")

ORDER_UNAUTHORIZED = (
    "No puedo consultar el estado de pedidos que no estén asociados a tu "
    "sesión. Soy el agente de soporte logístico de TrackFlow: verifica el "
    "número en tu confirmación de pedido o contacta con la marca que te lo "
    "envió. Si es tu pedido, puedo ayudarte con la devolución o con una "
    "incidencia."
)

ORDER_AUTH_UNAVAILABLE = (
    "No puedo verificar la autorización de ese pedido en este momento. "
    "Inténtalo de nuevo en unos minutos o contacta con tu marca."
)

ORDER_STOPWORDS = {
    "del",
    "los",
    "las",
    "que",
    "para",
    "con",
    "una",
    "unos",
    "unas",
    "por",
    "este",
    "esta",
    "estos",
    "estas",
    "estado",
    "status",
    "sigue",
    "siguiente",
    "numero",
    "num",
    "mismo",
    "otro",
    "otra",
    "ticket",
    "caso",
    "cliente",
    "marca",
}

_ORDER_WORD_RE = re.compile(
    r"(?:pedido|order|tracking|env[ií]o|gu[ií]a|paquete|parcel|shipment)"
    r"\s*(?:n[º°o.]*|#|id|number|n[uú]mero)?\s*[:#-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9-]{2,23})",
    re.IGNORECASE,
)

_HASH_ORDER_RE = re.compile(r"(?<![\w])#\s*(\d{4,12})\b")
_ORDER_CONTEXT_RE = re.compile(
    r"\b(?:pedido|order|tracking|env[ií]o|gu[ií]a|paquete|parcel|shipment)\b",
    re.IGNORECASE,
)


class OrderResolverError(RuntimeError):
    """No se pudo comprobar la propiedad del pedido (BD/servicio caído)."""


class OrderResolver(Protocol):
    def resolve(self, order_ref: str) -> "OrderOwner | None":
        ...


@dataclass(frozen=True)
class OrderOwner:
    order_ref: str
    owner_email: str
    owner_user_id: str | None = None
    country: str = "US"
    carrier: str = ""
    status: str = ""


@dataclass(frozen=True)
class OrderAuthorization:
    authorized: tuple[OrderOwner, ...] = ()
    unauthorized: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.unauthorized


def _valid_candidate(candidate: str) -> bool:
    value = (candidate or "").strip().strip("#:- ")
    if len(value) < 4 or len(value) > 24:
        return False
    if value.lower() in ORDER_STOPWORDS:
        return False
    if not re.search(r"\d", value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", value))


def extract_order_refs(question: str) -> list[str]:
    """Extrae referencias de pedido/tracking, evitando tickets y palabras."""

    text = question or ""
    refs: list[str] = []
    for match in _ORDER_WORD_RE.finditer(text):
        candidate = match.group(1)
        if _valid_candidate(candidate):
            refs.append(candidate.upper())
    if _ORDER_CONTEXT_RE.search(text):
        for match in _HASH_ORDER_RE.finditer(text):
            candidate = match.group(1)
            if _valid_candidate(candidate):
                refs.append(candidate.upper())
    return list(dict.fromkeys(refs))


def _matches_user(owner: OrderOwner, user: dict | None) -> bool:
    if not user:
        return False
    user_id = str(user.get("id") or "").strip()
    user_email = str(user.get("email") or "").strip().lower()
    owner_id = str(owner.owner_user_id or "").strip()
    owner_email = str(owner.owner_email or "").strip().lower()
    if user_email and owner_email and user_email == owner_email:
        return True
    if user_id and owner_id and user_id == owner_id:
        return True
    return False


def authorize_orders(
    refs: list[str],
    user: dict | None,
    resolver: OrderResolver | None,
) -> OrderAuthorization:
    """Comprueba que todas las referencias pertenecen al usuario autenticado."""

    if not refs:
        return OrderAuthorization()
    if not user:
        return OrderAuthorization(unauthorized=tuple(refs))
    if resolver is None:
        return OrderAuthorization(error="resolver_unavailable")

    authorized: list[OrderOwner] = []
    unauthorized: list[str] = []
    for ref in refs:
        try:
            owner = resolver.resolve(ref)
        except Exception as exc:  # noqa: BLE001 - se falla en cerrado
            logger.warning("No se pudo resolver el pedido %s: %s", ref, exc)
            return OrderAuthorization(error="resolver_unavailable")
        if owner is None or not _matches_user(owner, user):
            unauthorized.append(ref)
            continue
        authorized.append(owner)

    if unauthorized:
        return OrderAuthorization(
            authorized=tuple(authorized),
            unauthorized=tuple(unauthorized),
        )
    return OrderAuthorization(authorized=tuple(authorized))


class SqlOrderResolver:
    """Resolver por defecto: tabla ``customer_order`` de SQLModel."""

    def resolve(self, order_ref: str) -> OrderOwner | None:
        try:
            from sqlalchemy import func
            from sqlmodel import Session, select

            from database import engine
            from models import CustomerOrder
        except Exception as exc:  # noqa: BLE001 - sin configuración de BD
            raise OrderResolverError(str(exc)) from exc

        if engine is None:
            raise OrderResolverError("DATABASE_URL no configurada")

        try:
            with Session(engine) as session:
                row = session.exec(
                    select(CustomerOrder).where(
                        func.upper(CustomerOrder.order_ref)
                        == order_ref.upper()
                    )
                ).first()
        except Exception as exc:  # noqa: BLE001 - fail closed
            raise OrderResolverError(str(exc)) from exc

        if row is None:
            return None
        return OrderOwner(
            order_ref=str(row.order_ref),
            owner_email=str(row.owner_email or ""),
            owner_user_id=row.owner_user_id,
            country=str(row.country or "US").upper(),
            carrier=str(row.carrier or ""),
            status=str(row.status or ""),
        )


class InMemoryOrderResolver:
    """Resolver determinista para tests y demos sin base de datos."""

    def __init__(self, orders: dict[str, OrderOwner] | None = None) -> None:
        self._orders = {
            key.upper(): value for key, value in (orders or {}).items()
        }

    def resolve(self, order_ref: str) -> OrderOwner | None:
        return self._orders.get(order_ref.upper())


__all__ = [
    "ORDER_AUTH_UNAVAILABLE",
    "ORDER_UNAUTHORIZED",
    "InMemoryOrderResolver",
    "OrderAuthorization",
    "OrderOwner",
    "OrderResolver",
    "OrderResolverError",
    "SqlOrderResolver",
    "authorize_orders",
    "extract_order_refs",
]

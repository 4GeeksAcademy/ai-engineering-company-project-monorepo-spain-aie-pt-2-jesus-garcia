"""Tool de consulta de stock (solo lectura, in-process).

Reutiliza ``inventory_service.list_skus_with_stock``, la misma capa que sirve
``GET /inventory/products``. El stock se calcula desde las órdenes; no se lee
ni se modifica ningún contador almacenado.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from .contracts import (
    InventoryItem,
    InventoryLookupInput,
    InventoryLookupOutput,
)
from .execution import ToolTimeout, call_with_timeout, inventory_timeout_seconds

logger = logging.getLogger(__name__)

TOOL_NAME = "inventory_lookup"


def _read_inventory(payload: InventoryLookupInput) -> InventoryLookupOutput:
    from database import engine
    from sqlmodel import Session

    from ...services import inventory_service

    if engine is None:
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="unavailable",
            message="El servicio de inventario no está configurado.",
        )

    with Session(engine) as session:
        products = inventory_service.list_skus_with_stock(
            session,
            sku_id=payload.sku_id,
            sku_code=payload.sku_code,
            name_query=payload.name_query,
            warehouse=payload.warehouse,
        )

    items = [
        InventoryItem(
            id=product.id,
            name=product.name,
            sku_code=product.sku_code,
            warehouse=product.warehouse,
            client_id=product.client_id,
            min_stock=product.min_stock,
            current_stock=product.current_stock,
            current_stock_by_warehouse=product.current_stock_by_warehouse,
        )
        for product in products[: payload.limit]
    ]

    if not items:
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="not_found",
            message=(
                "No tengo constancia de stock para ese producto en el "
                "inventario."
            ),
        )

    return InventoryLookupOutput(ok=True, found=True, items=items)


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        message = str(errors[0].get("msg") or "Entrada inválida.")
        return message.removeprefix("Value error, ")
    return "Entrada inválida."


def lookup_inventory(
    payload: InventoryLookupInput | dict,
    *,
    timeout_seconds: float | None = None,
) -> InventoryLookupOutput:
    """Consulta stock en el inventario real, con timeout y fallback tipado."""
    if not isinstance(payload, InventoryLookupInput):
        try:
            payload = InventoryLookupInput.model_validate(payload)
        except ValidationError as exc:
            return InventoryLookupOutput(
                ok=False,
                found=False,
                error="invalid_input",
                message=_validation_message(exc),
            )

    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else inventory_timeout_seconds()
    )

    try:
        return call_with_timeout(lambda: _read_inventory(payload), timeout)
    except ToolTimeout:
        logger.warning(
            "Timeout consultando inventario tras %s segundos", timeout
        )
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="timeout",
            message="El servicio de inventario no respondió a tiempo.",
        )
    except Exception:  # noqa: BLE001 - se devuelve un fallback controlado
        logger.exception("Fallo consultando el inventario")
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error="unavailable",
            message="No se pudo consultar el inventario.",
        )


__all__ = ["TOOL_NAME", "lookup_inventory"]

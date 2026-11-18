"""Tools de inventario: consulta real y guard explícito de escritura.

El servidor MCP **no** expone ninguna mutación de inventario. La tool
``query_inventory`` lee ``GET /inventory/products`` (stock calculado desde las
órdenes). ``adjust_inventory_stock`` existe únicamente para rechazar de forma
explícita cualquier intento de escritura con el código ``INVENTORY_READ_ONLY``:
no llama a la API ni modifica nada.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..backend import get_api
from ..errors import ErrorCode, ToolFailure
from ..models import (
    InventoryItem,
    InventoryQueryOutput,
    InventoryWriteRejected,
    StockOperation,
    Warehouse,
)
from .guards import tool_guard

READ_SCOPE = "mcp:read"
WRITE_SCOPE = "mcp:write"


def _matches(item: InventoryItem, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    return needle in item.name.lower() or needle in item.sku_code.lower()


@tool_guard("query_inventory", READ_SCOPE)
async def query_inventory(
    sku_id: Annotated[
        int | None,
        Field(ge=1, description="ID numérico del producto (campo `id`)."),
    ] = None,
    sku_code: Annotated[
        str | None,
        Field(description="Código SKU exacto, por ejemplo CLT-SNK-W-42."),
    ] = None,
    name_query: Annotated[
        str | None,
        Field(description="Texto libre para buscar por nombre de producto."),
    ] = None,
    warehouse: Annotated[
        Warehouse | None,
        Field(
            description=(
                "Almacén: los_angeles o zaragoza. Si se indica, solo se "
                "devuelven productos con stock > 0 en ese almacén."
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=50, description="Máximo de productos a devolver (1-50)."),
    ] = 20,
) -> InventoryQueryOutput:
    """Consulta stock en tiempo real del gestor de inventario.

    El stock se calcula desde las órdenes inbound/outbound, nunca desde un
    contador almacenado. Sirve para preguntas como "¿tenemos stock de
    CLT-SNK-W-42?" o "¿qué hay en el almacén de Zaragoza?". La herramienta es
    de solo lectura: no existe ninguna operación de escritura de inventario.

    Requiere el scope `mcp:read`. Devuelve `ok=true, found=false` si no hay
    coincidencias.
    """
    payload = await get_api().get("/inventory/products")
    items = [InventoryItem.model_validate(item) for item in payload]

    if sku_id is not None:
        items = [item for item in items if item.id == sku_id]
    if sku_code:
        code = sku_code.strip().lower()
        items = [item for item in items if item.sku_code.lower() == code]
    if name_query:
        items = [item for item in items if _matches(item, name_query)]
    if warehouse:
        items = [
            item
            for item in items
            if int(item.current_stock_by_warehouse.get(warehouse, 0)) > 0
        ]

    items = items[:limit]
    return InventoryQueryOutput(
        ok=True,
        found=bool(items),
        items=items,
        message=(
            ""
            if items
            else "No hay productos que coincidan con la consulta de inventario."
        ),
    )


@tool_guard("adjust_inventory_stock", WRITE_SCOPE)
async def adjust_inventory_stock(
    sku_id: Annotated[
        int, Field(ge=1, description="ID del producto que se intentaría modificar.")
    ],
    quantity: Annotated[
        int, Field(gt=0, description="Cantidad que se intentaría mover.")
    ],
    operation: Annotated[
        StockOperation,
        Field(description="Operación solicitada: inbound u outbound."),
    ],
) -> InventoryWriteRejected:
    """Guard de escritura: rechaza siempre cualquier mutación de inventario.

    El MCP Server de TrackFlow expone el inventario en **solo lectura**. Esta
    tool existe para que un intento de escritura reciba un rechazo explícito y
    explicable (`INVENTORY_READ_ONLY`) en lugar de un error genérico o de un
    silencio. No llama a la API ni modifica stock.

    Requiere el scope `mcp:write` para que el rechazo sea de dominio; un token
    solo-lectura recibe antes `INSUFFICIENT_SCOPE`.
    """
    raise ToolFailure(
        ErrorCode.INVENTORY_READ_ONLY,
        (
            "El inventario de TrackFlow es de solo lectura en este servidor MCP. "
            "No se ha modificado ningún stock."
        ),
        details={
            "requested_operation": operation,
            "sku_id": sku_id,
            "quantity": quantity,
            "writable": False,
            "hint": (
                "Usa query_inventory para consultar el stock. Las entradas y "
                "salidas se registran en el backoffice de operaciones, no por MCP."
            ),
        },
    )


def register_inventory_tools(mcp: FastMCP) -> None:
    mcp.tool(
        name="query_inventory",
        description=(
            "Consulta en tiempo real el stock por SKU y almacén en el gestor de "
            "inventario. Solo lectura. Requiere scope mcp:read."
        ),
    )(query_inventory)
    mcp.tool(
        name="adjust_inventory_stock",
        description=(
            "Guard de solo lectura: cualquier intento de modificar stock se "
            "rechaza explícitamente con INVENTORY_READ_ONLY. Requiere mcp:write."
        ),
    )(adjust_inventory_stock)


__all__ = [
    "adjust_inventory_stock",
    "query_inventory",
    "register_inventory_tools",
]

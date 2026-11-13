"""Tools del agente: contratos, timeout y cliente MCP.

El agente NO accede directamente a TinyDB/SQLModel ni a los servicios REST: las
dos tools se cargan e invocan desde el MCP Server mediante
``langchain-mcp-adapters``. Los nombres lógicos ``incident_lookup`` e
``inventory_lookup`` se conservan en el estado/traces; por debajo llaman a
``query_incidents`` y ``query_inventory`` del MCP.
"""

from __future__ import annotations

from .contracts import (
    IncidentLookup,
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
    InventoryItem,
    InventoryLookup,
    InventoryLookupInput,
    InventoryLookupOutput,
)
from .execution import (
    DEFAULT_INCIDENT_TIMEOUT_SECONDS,
    DEFAULT_INVENTORY_TIMEOUT_SECONDS,
    ToolTimeout,
    call_with_timeout,
    incident_timeout_seconds,
    inventory_timeout_seconds,
)
from .mcp_auth import MCPAuthError, MCPSettings, MCPTokenProvider
from .mcp_client import (
    INCIDENT_TOOL_NAME,
    INVENTORY_TOOL_NAME,
    MCP_INCIDENT_TOOL,
    MCP_INVENTORY_TOOL,
    MCPToolClient,
    MCPToolError,
    get_mcp_client,
    lookup_incident,
    lookup_inventory,
    mcp_timeout_seconds,
    set_mcp_client_for_tests,
)

__all__ = [
    "DEFAULT_INCIDENT_TIMEOUT_SECONDS",
    "DEFAULT_INVENTORY_TIMEOUT_SECONDS",
    "INCIDENT_TOOL_NAME",
    "INVENTORY_TOOL_NAME",
    "MCP_INCIDENT_TOOL",
    "MCP_INVENTORY_TOOL",
    "MCPAuthError",
    "MCPSettings",
    "MCPToolClient",
    "MCPToolError",
    "MCPTokenProvider",
    "IncidentLookup",
    "IncidentLookupInput",
    "IncidentLookupOutput",
    "IncidentRecord",
    "InventoryItem",
    "InventoryLookup",
    "InventoryLookupInput",
    "InventoryLookupOutput",
    "ToolTimeout",
    "call_with_timeout",
    "get_mcp_client",
    "incident_timeout_seconds",
    "inventory_timeout_seconds",
    "lookup_incident",
    "lookup_inventory",
    "mcp_timeout_seconds",
    "set_mcp_client_for_tests",
]

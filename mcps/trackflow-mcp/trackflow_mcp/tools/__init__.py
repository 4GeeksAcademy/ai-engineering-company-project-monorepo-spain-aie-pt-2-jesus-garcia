"""Tools expuestas por el servidor MCP."""

from .incidents import register_incident_tools
from .inventory import register_inventory_tools

__all__ = ["register_incident_tools", "register_inventory_tools"]

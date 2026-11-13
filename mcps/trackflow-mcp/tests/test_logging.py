"""Tests del log estructurado por invocación de tool."""

from __future__ import annotations

import json
import logging

from trackflow_mcp.logs import TOOL_LOGGER_NAME, sanitize_arguments
from trackflow_mcp.tools.inventory import query_inventory


def _records(caplog):
    return [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == TOOL_LOGGER_NAME
    ]


async def test_each_invocation_logs_client_tool_and_outcome(
    read_auth, fake_api, caplog
):
    fake_api.on("GET", "/inventory/products", [])
    caplog.set_level(logging.INFO, logger=TOOL_LOGGER_NAME)

    await query_inventory(sku_code="CLT-SNK-W-42")

    records = _records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "tool_invocation"
    assert record["tool"] == "query_inventory"
    assert record["client_id"] == "test-client"
    assert record["subject"] == "user-1"
    assert record["scopes"] == ["mcp:read"]
    assert record["outcome"] == "success"
    assert record["error_code"] is None
    assert "duration_ms" in record
    assert record["arguments"]["sku_code"] == "CLT-SNK-W-42"


async def test_denied_invocation_logs_error_code(
    read_auth, fake_api, caplog
):
    caplog.set_level(logging.INFO, logger=TOOL_LOGGER_NAME)

    from mcp.server.fastmcp.exceptions import ToolError
    import pytest

    with pytest.raises(ToolError):
        from trackflow_mcp.tools.inventory import adjust_inventory_stock

        await adjust_inventory_stock(sku_id=1, quantity=1, operation="inbound")

    records = _records(caplog)
    assert records[0]["outcome"] == "denied"
    assert records[0]["error_code"] == "INSUFFICIENT_SCOPE"
    assert fake_api.calls == []


def test_sanitize_arguments_redacts_secrets_and_truncates():
    cleaned = sanitize_arguments(
        {
            "token": "secret",
            "password": "secret",
            "description": "x" * 500,
            "nested": {"access_token": "secret", "ok": 1},
        }
    )
    assert cleaned["token"] == "***"
    assert cleaned["password"] == "***"
    assert cleaned["nested"]["access_token"] == "***"
    assert cleaned["nested"]["ok"] == 1
    assert cleaned["description"].endswith("…")
    assert len(cleaned["description"]) <= 201

#!/usr/bin/env python3
"""Smoke test del MCP Server: discovery + un flujo por tool.

Uso:
    python scripts/mcp_smoke.py --token "$TOKEN"
    python scripts/mcp_smoke.py --client-id ... --client-secret ...
    python scripts/mcp_smoke.py --write   # crea y mueve una incidencia real

Exit codes:
    0  todo correcto
    1  una tool devolvió un error inesperado
    2  fallo de autenticación (401/403)
    3  fallo de configuración/conexión
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE, override=False)


def _text(result: Any) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    text = _text(result)
    try:
        return json.loads(text)
    except ValueError:
        return text


def _token_from_provider(args) -> str:
    if args.token:
        return args.token
    if not (args.token_url and args.client_id and args.client_secret):
        raise SystemExit(
            "Falta --token o las credenciales M2M "
            "(--token-url/--client-id/--client-secret)."
        )
    data = {
        "grant_type": "client_credentials",
        "client_id": args.client_id,
        "client_secret": args.client_secret,
    }
    if args.audience:
        data["audience"] = args.audience
    if args.resource:
        data["resource"] = args.resource
    if args.scopes:
        data["scope"] = args.scopes
    response = httpx.post(args.token_url, data=data, timeout=15)
    if response.status_code >= 400:
        raise SystemExit(
            f"El proveedor OAuth rechazó el token: HTTP {response.status_code} "
            f"{response.text[:300]}"
        )
    return str(response.json()["access_token"])


async def _call(session: ClientSession, name: str, arguments: dict) -> Any:
    result = await session.call_tool(name, arguments)
    print(f"\n[{name}] isError={result.isError}")
    print(json.dumps(_payload(result), ensure_ascii=False, indent=2, default=str))
    return result


async def run(args) -> int:
    token = _token_from_provider(args)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with streamablehttp_client(args.url, headers=headers) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("TOOLS")
                for tool in tools.tools:
                    print(
                        f"- {tool.name}: {tool.description}\n"
                        f"  input={json.dumps(tool.inputSchema, ensure_ascii=False)}"
                    )

                if args.skip_calls:
                    return 0

                incident_id = args.incident_id
                if not incident_id:
                    listing = await _call(
                        session, "query_incidents", {"limit": 1}
                    )
                    payload = _payload(listing)
                    incidents = (
                        payload.get("incidents", [])
                        if isinstance(payload, dict)
                        else []
                    )
                    if incidents:
                        incident_id = str(incidents[0]["id"])

                if incident_id:
                    await _call(
                        session, "query_incidents", {"incident_id": incident_id}
                    )
                await _call(session, "get_incident_summary", {})
                await _call(
                    session,
                    "query_inventory",
                    {"sku_code": args.sku_code},
                )

                rejected = await _call(
                    session,
                    "adjust_inventory_stock",
                    {"sku_id": args.sku_id, "quantity": 1, "operation": "inbound"},
                )
                if not rejected.isError:
                    print(
                        "ERROR: adjust_inventory_stock debía rechazar la escritura",
                        file=sys.stderr,
                    )
                    return 1

                if args.write:
                    created = await _call(
                        session,
                        "create_incident",
                        {
                            "title": args.incident_title,
                            "description": "Incidencia creada por el smoke test del MCP.",
                            "origin": "internal",
                            "branch": "central",
                            "category": "other",
                        },
                    )
                    payload = _payload(created)
                    new_id = payload["incident"]["id"]
                    await _call(
                        session,
                        "update_incident_status",
                        {"incident_id": str(new_id), "status": "in_progress"},
                    )
        return 0
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            print(f"AUTH ERROR {exc.response.status_code}: {exc}", file=sys.stderr)
            return 2
        print(f"HTTP ERROR: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if "401" in text or "403" in text or "invalid_token" in text:
            print(f"AUTH ERROR: {text}", file=sys.stderr)
            return 2
        print(f"CONNECTION ERROR: {text}", file=sys.stderr)
        return 3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("MCP_RESOURCE_URL", "http://localhost:8001/mcp"),
    )
    parser.add_argument("--token", default=os.getenv("MCP_AGENT_BEARER_TOKEN", ""))
    parser.add_argument(
        "--token-url",
        default=os.getenv("MCP_OAUTH_TOKEN_URL")
        or os.getenv("AUTH0_TOKEN_URL", ""),
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("MCP_OAUTH_CLIENT_ID")
        or os.getenv("AUTH0_M2M_CLIENT_ID", ""),
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("MCP_OAUTH_CLIENT_SECRET")
        or os.getenv("AUTH0_M2M_CLIENT_SECRET", ""),
    )
    parser.add_argument(
        "--audience",
        default=os.getenv("MCP_OAUTH_AUDIENCE")
        or os.getenv("AUTH0_M2M_AUDIENCE", ""),
    )
    parser.add_argument(
        "--resource",
        default=os.getenv("MCP_OAUTH_RESOURCE")
        or os.getenv("AUTH0_M2M_RESOURCE", ""),
    )
    parser.add_argument(
        "--scopes",
        default=os.getenv("MCP_OAUTH_SCOPES")
        or os.getenv("AUTH0_M2M_SCOPES", "mcp:read"),
    )
    parser.add_argument("--incident-id", default="")
    parser.add_argument("--sku-code", default="CLT-SNK-W-42")
    parser.add_argument("--sku-id", type=int, default=1)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--incident-title",
        default="MCP Playground validation",
    )
    parser.add_argument("--skip-calls", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

# `mcps` folder

This folder contains **Model Context Protocol (MCP) Servers** that expose tools, resources, and context to AI models and agents.

Each subfolder inside `mcps/` must correspond to **one specific MCP server** (for example: `database-mcp`, `github-mcp`) and include its own documentation.

- **Main purpose**: to centralize the servers that bridge the gap between AI models and the company's internal systems or data sources.
- **Recommendation**: document the tools and resources exposed by each MCP server.

## Servers

| Server | Description |
|---|---|
| [`trackflow-mcp`](./trackflow-mcp/README.md) | OAuth 2.1-protected operations server: real-time incidents, ticket lifecycle and read-only inventory. |

> _Spanish version: [README.es.md](./README.es.md)._

"""SignalK MCP server.

Exposes signalk-mcp tools to any MCP-compatible client (Hermes Agent, Claude Code, etc.).
Reads SignalK URL from the SIGNALK_URL environment variable.
"""

from __future__ import annotations

import asyncio
import json
import os

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import battery_state, get_route, read_sensor


def build_server() -> Server:
    """Construct and configure the MCP server with all tools registered."""
    server = Server("signalk-mcp")
    base_url = os.environ.get("SIGNALK_URL", "http://localhost:3000")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="read_sensor",
                description="Read a SignalK path's current value and timestamp.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "SignalK dotted path (e.g. 'environment.wind.speedTrue').",
                        }
                    },
                    "required": ["path"],
                },
            ),
            types.Tool(
                name="get_route",
                description="Get the currently active route with waypoints.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="battery_state",
                description="Get state of charge, voltage, current for a battery bank.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "bank": {
                            "type": "string",
                            "default": "house",
                            "description": "Battery bank name (default 'house').",
                        }
                    },
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, args: dict) -> list[types.TextContent]:
        client = SignalKClient(base_url=base_url)
        try:
            if name == "read_sensor":
                result = await read_sensor(client, args["path"])
            elif name == "get_route":
                result = await get_route(client)
            elif name == "battery_state":
                result = await battery_state(client, bank=args.get("bank", "house"))
            else:
                raise ValueError(f"Unknown tool: {name}")
        finally:
            await client.aclose()

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


def main() -> None:
    """Run the signalk-mcp server over stdio."""
    server = build_server()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()

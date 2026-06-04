"""SignalK MCP server.

Exposes signalk-mcp tools to any MCP-compatible client (Hermes Agent, Claude Code, etc.).
Reads SignalK URL from the SIGNALK_URL environment variable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import (
    battery_state,
    depth_state,
    get_local_time,
    get_route,
    list_paths,
    read_sensor,
)

logger = logging.getLogger(__name__)


def build_server(client: SignalKClient) -> Server:
    """Construct and configure the MCP server with all tools registered.

    The caller owns ``client`` and must close it on shutdown. One client is
    shared across every tool call so httpx connection pooling works.
    """
    server = Server("signalk-mcp")

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
                inputSchema={"type": "object", "properties": {}},
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
            types.Tool(
                name="depth_state",
                description=(
                    "Water depth with under-keel clearance first. Use this for "
                    "'how's our depth?' and 'how close are we to running aground?' — "
                    "below_keel_m IS the clearance under the hull (no draft math needed). "
                    "Do not guess depth paths or compute clearance yourself; call this."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_local_time",
                description="Get current time localized to the vessel's GPS position.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="list_paths",
                description=(
                    "Discover which SignalK paths this vessel publishes, with units and "
                    "descriptions. Call this before guessing a path name (depth is "
                    "'environment.depth.belowTransducer', not 'sensors.depth'). Optional "
                    "'prefix' filters results (e.g. 'navigation', 'environment.depth')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prefix": {
                            "type": "string",
                            "description": "Only return paths starting with this string.",
                        }
                    },
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, args: dict | None) -> list[types.TextContent]:
        args = args or {}
        if name == "read_sensor":
            result = await read_sensor(client, args["path"])
        elif name == "get_route":
            result = await get_route(client)
        elif name == "battery_state":
            result = await battery_state(client, bank=args.get("bank", "house"))
        elif name == "depth_state":
            result = await depth_state(client)
        elif name == "get_local_time":
            result = await get_local_time(client)
        elif name == "list_paths":
            result = await list_paths(client, prefix=args.get("prefix"))
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


def main() -> None:
    """Run the signalk-mcp server over stdio."""
    base_url = os.environ.get("SIGNALK_URL", "http://localhost:3000")
    client = SignalKClient(base_url=base_url)
    server = build_server(client)

    async def _run() -> None:
        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )
        finally:
            await client.aclose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()

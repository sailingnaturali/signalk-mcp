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

from signalk_mcp import tools
from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import (
    battery_state,
    depth_state,
    get_active_alarms,
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
                name="get_active_alarms",
                description=(
                    "Use this for 'anything wrong?' / 'systems check' / 'any alarms?' — "
                    "returns active SignalK notifications (alarms/warnings), most severe "
                    "first. Do NOT poll individual paths via read_sensor to check for "
                    "trouble; this surfaces every active notification at once. Each entry's "
                    "`path` is the monitored SignalK path — pass it to vessel-knowledge "
                    "explain_notification to triage. Empty list means all systems nominal."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="read_sensor",
                description=(
                    "GENERIC fallback reader for any SignalK path's current value and "
                    "timestamp. Prefer the dedicated tools for common readings — they "
                    "return the safety-correct path with proper labelling: for depth / "
                    "under-keel clearance use depth_state; for battery state of charge / "
                    "voltage use battery_state; for alarms and warnings use "
                    "get_active_alarms. Use read_sensor ONLY for paths without a dedicated "
                    "tool (e.g. 'environment.wind.speedTrue', 'navigation.speedOverGround'). "
                    "Reading a raw depth path here is NOT under-keel depth — use depth_state."
                ),
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
                description=(
                    "Use this for 'what's our battery' / 'state of charge' / 'how's the "
                    "house bank' — returns state of charge, voltage, and current for a "
                    "battery bank with correct labelling and units. Do NOT read battery "
                    "values via read_sensor; this tool resolves the right bank paths for you."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "bank": {
                            "type": "string",
                            "default": "0",
                            "description": "Battery bank instance. Omit it to let the tool find the vessel's bank (tries '0', then discovers named banks like 'house'). Only pass this to target a specific bank.",
                        }
                    },
                },
            ),
            types.Tool(
                name="depth_state",
                description=(
                    "Use this for 'what's our depth?' / 'how much under the keel?' / "
                    "'how close are we to running aground?' — returns water depth with "
                    "under-keel clearance first. below_keel_m IS the clearance under the "
                    "hull (no draft math needed). Do NOT read depth via read_sensor: the "
                    "raw transducer path (environment.depth.belowTransducer) is NOT "
                    "under-keel depth and will mislead. Do not guess depth paths or "
                    "compute clearance yourself; call this."
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
    async def _call_tool(
        name: str, args: dict | None
    ) -> list[types.TextContent] | tuple[list[types.TextContent], dict]:
        args = args or {}
        if name == "get_active_alarms":
            result = await get_active_alarms(client)
        elif name == "read_sensor":
            result = await read_sensor(client, args.get("path", ""))
        elif name == "get_route":
            result = await get_route(client)
        elif name == "battery_state":
            result = await battery_state(client, bank=args.get("bank"))
        elif name == "depth_state":
            result = await depth_state(client)
        elif name == "get_local_time":
            result = await get_local_time(client)
        elif name == "list_paths":
            result = await list_paths(client, prefix=args.get("prefix"))
        else:
            raise ValueError(f"Unknown tool: {name}")

        # PILOT (2026-08-10), depth_state only. The bug: `display` sits BELOW the raw
        # SI fields in the JSON dump, so a model reading top-down meets `below_keel_m`
        # first and re-renders from it, dropping units. Asking the model not to - the
        # SOUL verbatim carve-out - failed on DeepSeek V4 Flash and Sonnet alike.
        #
        # Returning (content, structuredContent) was tried first and is a dead end on
        # at least one client: OpenClaw renders structuredContent and DISCARDS the text
        # content, so the sentence never reached the model and the payload was byte-for
        # -byte the old one. Ordering inside a single text block is the only lever that
        # survives both clients. Sentence first, numbers after, still available for
        # threshold reasoning but no longer the first thing read.
        #
        # Deliberately NOT rolled out to the other six yet: depth_state alone means one
        # "depth and battery" ask A/Bs this against the old shape in a single reply.
        if name == "depth_state" and isinstance(result, dict) and result.get("display"):
            rest = {k: v for k, v in result.items() if k != "display"}
            text = f"{result['display']}\n\n{json.dumps(rest, indent=2)}"
            return [types.TextContent(type="text", text=text)]

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


def main() -> None:
    """Run the signalk-mcp server over stdio."""
    base_url = os.environ.get("SIGNALK_URL", "http://localhost:3000")
    client = SignalKClient(base_url=base_url)
    server = build_server(client)

    async def _run() -> None:
        # Warm the ~50 MB TimezoneFinder off-thread so the first
        # get_local_time call doesn't pay construction on the event loop.
        warmup = asyncio.create_task(asyncio.to_thread(tools._get_timezone_finder))
        warmup.add_done_callback(lambda t: t.exception())   # never unraised
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

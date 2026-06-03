"""End-to-end dispatcher test: invoke each tool through the MCP server's
list_tools / call_tool registration to catch name typos and arg-shape drift."""

import json
import os

import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.server import build_server


def _setup_position_mock() -> None:
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/position"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"value": {"latitude": 48.43, "longitude": -123.37}, "timestamp": "2026-05-21T00:00:00Z"},
        )
    )


@pytest.fixture
async def server():
    client = SignalKClient(base_url="http://signalk-test:3000")
    try:
        yield build_server(client)
    finally:
        await client.aclose()


async def _call_registered_tool(server, name: str, args: dict | None):
    """Pull the registered call_tool handler off the server and invoke it."""
    handler = server.request_handlers
    # MCP Server registers handlers by request type; locate the call_tool by name.
    # We rely on the server exposing _tool_handlers / call_tool via the SDK.
    from mcp.types import CallToolRequest, CallToolRequestParams

    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=args),
    )
    fn = handler[CallToolRequest]
    result = await fn(req)
    return result


@respx.mock
async def test_dispatch_read_sensor(server) -> None:
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/wind/speedTrue"
    ).mock(return_value=httpx.Response(200, json={"value": 5.0, "timestamp": "2026-05-21T00:00:00Z"}))

    result = await _call_registered_tool(server, "read_sensor", {"path": "environment.wind.speedTrue"})
    payload = json.loads(result.root.content[0].text)
    assert payload["value"] == 5.0


@respx.mock
async def test_dispatch_battery_state_defaults(server) -> None:
    """call_tool must accept arguments=None (some MCP clients omit it)."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/house"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "capacity": {"stateOfCharge": {"value": 0.5, "timestamp": "2026-05-21T00:00:00Z"}},
                "voltage": {"value": 12.6, "timestamp": "2026-05-21T00:00:00Z"},
                "current": {"value": -1.0, "timestamp": "2026-05-21T00:00:00Z"},
            },
        )
    )
    result = await _call_registered_tool(server, "battery_state", None)
    payload = json.loads(result.root.content[0].text)
    assert payload["bank"] == "house"


@respx.mock
async def test_dispatch_get_local_time(server) -> None:
    _setup_position_mock()
    result = await _call_registered_tool(server, "get_local_time", {})
    payload = json.loads(result.root.content[0].text)
    assert "display" in payload
    assert "iana_timezone" in payload


async def test_list_tools_includes_all_tools(server) -> None:
    from mcp.types import ListToolsRequest

    handler = server.request_handlers[ListToolsRequest]
    req = ListToolsRequest(method="tools/list")
    result = await handler(req)
    names = {tool.name for tool in result.root.tools}
    assert names == {"read_sensor", "get_route", "battery_state", "get_local_time", "list_paths"}


@respx.mock
async def test_dispatch_list_paths(server) -> None:
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "environment": {
                    "depth": {
                        "belowTransducer": {
                            "value": 27.1,
                            "meta": {"units": "m", "description": "Depth below Transducer"},
                        }
                    }
                }
            },
        )
    )
    result = await _call_registered_tool(server, "list_paths", {})
    payload = json.loads(result.root.content[0].text)
    assert payload["count"] == 1
    assert payload["paths"][0]["path"] == "environment.depth.belowTransducer"

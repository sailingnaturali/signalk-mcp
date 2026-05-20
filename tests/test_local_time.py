"""Tests for get_local_time tool."""

import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import get_local_time


def _mock_position(lat: float, lon: float) -> None:
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/position"
    ).mock(return_value=httpx.Response(
        200,
        json={"value": {"latitude": lat, "longitude": lon}, "timestamp": "2026-05-20T18:54:00Z"},
    ))


@respx.mock
async def test_local_time_pacific_northwest():
    """Victoria BC (48.43, -123.37) should resolve to America/Vancouver."""
    _mock_position(48.43, -123.37)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_local_time(client)

    assert result["timezone"] == "America/Vancouver"
    assert "UTC" not in result["display"]
    assert result["utc"] is not None
    assert result["local"] is not None


@respx.mock
async def test_local_time_display_format():
    """display field should be HH:MM only (e.g. '11:54')."""
    _mock_position(48.43, -123.37)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_local_time(client)

    parts = result["display"].split()
    assert len(parts) == 1       # no timezone abbreviation
    assert ":" in parts[0]       # time part HH:MM


@respx.mock
async def test_local_time_falls_back_to_utc_when_no_position():
    """Falls back to UTC if position value is null."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/position"
    ).mock(return_value=httpx.Response(
        200,
        json={"value": None, "timestamp": "2026-05-20T18:54:00Z"},
    ))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_local_time(client)

    assert result["timezone"] == "UTC"
    assert ":" in result["display"]

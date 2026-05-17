"""Integration test — requires a running SignalK server with playback data.

Set SIGNALK_TEST_URL to enable (skipped otherwise).

Usage:
    SIGNALK_TEST_URL=http://naturali-signalk.local:3000 uv run pytest tests/test_integration_signalk.py -v
"""

import os

import pytest

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import read_sensor

SIGNALK_URL = os.environ.get("SIGNALK_TEST_URL")
pytestmark = pytest.mark.skipif(
    not SIGNALK_URL,
    reason="Set SIGNALK_TEST_URL to enable integration tests.",
)


async def test_read_position_from_live_signalk():
    """Read navigation.position from a live SignalK; expect a coordinate pair."""
    client = SignalKClient(base_url=SIGNALK_URL)
    try:
        result = await read_sensor(client, "navigation.position")
        assert result["value"] is not None, "SignalK returned no position value"
        pos = result["value"]
        assert "longitude" in pos and "latitude" in pos
        assert -180 <= pos["longitude"] <= 180
        assert -90 <= pos["latitude"] <= 90
    finally:
        await client.aclose()


async def test_read_wind_speed_from_live_signalk():
    """Read wind speed from a live SignalK; expect a numeric value."""
    client = SignalKClient(base_url=SIGNALK_URL)
    try:
        result = await read_sensor(client, "environment.wind.speedTrue")
        assert result["value"] is not None, "SignalK returned no wind speed"
        assert isinstance(result["value"], (int, float))
    finally:
        await client.aclose()

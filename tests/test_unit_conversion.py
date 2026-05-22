"""Tests for human-readable unit conversion in read_sensor."""

import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import read_sensor


def _mock_sensor(path: str, value: float):
    url_path = path.replace(".", "/")
    respx.get(
        f"http://signalk-test:3000/signalk/v1/api/vessels/self/{url_path}"
    ).mock(return_value=httpx.Response(200, json={"value": value, "timestamp": "2026-05-18T00:00:00Z"}))


@respx.mock
async def test_wind_speed_converts_to_knots():
    _mock_sensor("environment.wind.speedTrue", 8.5)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.speedTrue")
    assert result["display"] == "16.5 knots"
    assert result["unit"] == "knots"


@respx.mock
async def test_sog_converts_to_knots():
    _mock_sensor("navigation.speedOverGround", 3.0)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.speedOverGround")
    assert result["display"] == "5.8 knots"
    assert result["unit"] == "knots"


@respx.mock
async def test_heading_converts_to_degrees_with_compass():
    _mock_sensor("navigation.headingTrue", 2.268)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.headingTrue")
    assert result["display"] == "129.9° (South-East)"
    assert result["unit"] == "°"


@respx.mock
async def test_wind_angle_uses_port_starboard():
    """Relative wind angle (signed) → 'off the X bow', not compass label.
    5.498 rad ≈ 315° wraps to -45° → 45° to port."""
    _mock_sensor("environment.wind.angleTrueWater", 5.498)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.angleTrueWater")
    assert result["display"] == "45° off the port bow"
    assert result["unit"] == "°"


@respx.mock
async def test_pressure_converts_to_hpa():
    _mock_sensor("environment.outside.pressure", 101000.0)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.outside.pressure")
    assert result["display"] == "1010.0 hPa"
    assert result["unit"] == "hPa"


@respx.mock
async def test_temperature_converts_to_celsius():
    _mock_sensor("environment.outside.temperature", 286.15)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.outside.temperature")
    assert result["display"] == "13.0°C"
    assert result["unit"] == "°C"


@respx.mock
async def test_depth_stays_in_metres():
    _mock_sensor("environment.depth.belowKeel", 38.0)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.depth.belowKeel")
    assert result["display"] == "38.0 m"
    assert result["unit"] == "m"


@respx.mock
async def test_unknown_path_has_no_display():
    """Paths with no known conversion return display=None, unit=None."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/some/unknown/path"
    ).mock(return_value=httpx.Response(
        200, json={"value": 42.0, "timestamp": "2026-05-18T00:00:00Z"}
    ))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "some.unknown.path")
    assert result["display"] is None
    assert result["unit"] is None


@respx.mock
async def test_position_formats_with_cardinal_directions():
    """navigation.position formats latitude and longitude with full cardinal names."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/position"
    ).mock(return_value=httpx.Response(
        200, json={"value": {"latitude": 48.76, "longitude": -123.05}, "timestamp": "2026-05-18T00:00:00Z"}
    ))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.position")
    assert result["display"] == "48.7600 North, 123.0500 West"
    assert result["unit"] == "°"
    assert result["value"] == {"latitude": 48.76, "longitude": -123.05}

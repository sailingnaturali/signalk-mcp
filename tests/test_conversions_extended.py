"""New conversions and TTS-protection contracts added in this pass."""

import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import read_sensor


def _mock(path: str, value):
    url_path = path.replace(".", "/")
    respx.get(
        f"http://signalk-test:3000/signalk/v1/api/vessels/self/{url_path}"
    ).mock(return_value=httpx.Response(200, json={"value": value, "timestamp": "2026-05-21T00:00:00Z"}))


@respx.mock
async def test_apparent_wind_uses_correct_signalk_path_name():
    """SignalK calls it 'angleApparent', not 'angleApparentWater'.
    The conversion table must use the canonical name."""
    import math
    _mock("environment.wind.angleApparent", math.radians(45))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.angleApparent")
    assert "starboard" in result["display"].lower()
    assert "45" in result["display"]
    await client.aclose()


@respx.mock
async def test_relative_wind_negative_is_port():
    """Signed relative wind angle: negative = port."""
    import math
    _mock("environment.wind.angleApparent", math.radians(-30))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.angleApparent")
    assert "port" in result["display"].lower()
    assert "30" in result["display"]
    await client.aclose()


@respx.mock
async def test_true_wind_direction_compass():
    """environment.wind.directionTrue is a compass bearing — needs compass label."""
    import math
    _mock("environment.wind.directionTrue", math.radians(90))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.directionTrue")
    assert result["display"] == "90.0° (East)"
    assert result["unit"] == "°"
    await client.aclose()


@respx.mock
async def test_magnetic_variation_signed_east():
    """Positive magneticVariation is east, negative west — display must indicate."""
    import math
    _mock("navigation.magneticVariation", math.radians(15.5))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.magneticVariation")
    assert "east" in result["display"].lower()
    await client.aclose()


@respx.mock
async def test_magnetic_variation_signed_west():
    import math
    _mock("navigation.magneticVariation", math.radians(-5.0))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.magneticVariation")
    assert "west" in result["display"].lower()
    await client.aclose()

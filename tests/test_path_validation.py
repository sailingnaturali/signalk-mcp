"""Path validation: agent-supplied path/bank strings must be sanitized
before being interpolated into the SignalK URL."""

import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import battery_state, read_sensor


@pytest.mark.parametrize(
    "bad_path",
    [
        "../resources/routes/r-1",
        "navigation/position",  # slashes not allowed
        "navigation.position; rm -rf /",
        "",
        "name with spaces",
    ],
)
async def test_read_sensor_rejects_invalid_path(bad_path: str) -> None:
    client = SignalKClient(base_url="http://signalk-test:3000")
    with pytest.raises(ValueError, match="invalid path"):
        await read_sensor(client, bad_path)
    await client.aclose()


@pytest.mark.parametrize(
    "bad_bank",
    ["../foo", "house/../engine", "house bank", ""],
)
async def test_battery_state_rejects_invalid_bank(bad_bank: str) -> None:
    client = SignalKClient(base_url="http://signalk-test:3000")
    with pytest.raises(ValueError, match="invalid"):
        await battery_state(client, bank=bad_bank)
    await client.aclose()


@respx.mock
async def test_read_sensor_accepts_normal_dotted_path() -> None:
    """Sanity: well-formed paths still work."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/wind/speedTrue"
    ).mock(return_value=httpx.Response(200, json={"value": 5.0, "timestamp": "2026-05-21T00:00:00Z"}))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.speedTrue")
    assert result["value"] == 5.0
    await client.aclose()

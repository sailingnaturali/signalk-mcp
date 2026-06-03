import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import read_sensor


@respx.mock
async def test_read_sensor_returns_value_for_known_path():
    """read_sensor returns the value and timestamp from SignalK for a known path."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/wind/speedTrue"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"value": 12.5, "timestamp": "2026-05-14T18:00:00Z"},
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.wind.speedTrue")

    assert result["value"] == 12.5
    assert result["timestamp"] == "2026-05-14T18:00:00Z"
    assert result["path"] == "environment.wind.speedTrue"


@respx.mock
async def test_read_sensor_returns_null_for_absent_path():
    """A 404 means the vessel doesn't publish that path — a normal 'unavailable'
    result, not an error. read_sensor must NOT raise, so a string of guessed/
    missing paths can't trip a client's consecutive-failure circuit breaker."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/headingTrue"
    ).mock(return_value=httpx.Response(404))

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.headingTrue")

    assert result["value"] is None
    assert result["display"] is None
    assert result["path"] == "navigation.headingTrue"


@respx.mock
async def test_read_sensor_raises_on_server_error():
    """A real failure (5xx, connection) is NOT a missing path and must still
    surface as an error so genuine outages are visible to the client."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/speedOverGround"
    ).mock(return_value=httpx.Response(500))

    client = SignalKClient(base_url="http://signalk-test:3000")

    with pytest.raises(httpx.HTTPStatusError):
        await read_sensor(client, "navigation.speedOverGround")

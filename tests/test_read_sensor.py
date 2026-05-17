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
async def test_read_sensor_raises_on_unknown_path():
    """read_sensor surfaces HTTP errors clearly."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/no/such/thing"
    ).mock(return_value=httpx.Response(404))

    client = SignalKClient(base_url="http://signalk-test:3000")

    with pytest.raises(httpx.HTTPStatusError):
        await read_sensor(client, "no.such.thing")

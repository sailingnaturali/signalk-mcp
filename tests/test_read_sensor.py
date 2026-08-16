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
async def test_absent_path_is_distinguishable_from_a_quiet_sensor():
    """The two must not look alike to the caller.

    A 404 means this vessel has no such sensor; a published path whose value is
    currently null means the sensor exists and just isn't reporting. Collapsing
    both into ``value: None`` is what lets an agent narrate a barometer the boat
    has never had.
    """
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/outside/pressure"
    ).mock(return_value=httpx.Response(404))
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/wind/speedTrue"
    ).mock(return_value=httpx.Response(200, json={"value": None, "timestamp": None}))

    client = SignalKClient(base_url="http://signalk-test:3000")
    absent = await read_sensor(client, "environment.outside.pressure")
    quiet = await read_sensor(client, "environment.wind.speedTrue")

    assert absent["available"] is False
    assert quiet["available"] is True
    assert absent != quiet
    # The absent case must say so in words the model can't read as a reading.
    assert "does not publish" in absent["note"].lower()
    assert "environment.outside.pressure" in absent["note"]
    assert quiet["note"] is None


@respx.mock
async def test_available_path_with_a_reading_carries_no_note():
    """A live value is the ordinary case and must stay uncluttered."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/speedOverGround"
    ).mock(return_value=httpx.Response(200, json={"value": 3.5, "timestamp": "2026-08-16T12:00:00Z"}))

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "navigation.speedOverGround")

    assert result["available"] is True
    assert result["note"] is None
    assert result["value"] == 3.5


@respx.mock
async def test_absent_path_carries_no_unit():
    """A unit on an absent path implies a sensor that exists but is quiet."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/outside/temperature"
    ).mock(return_value=httpx.Response(404))

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await read_sensor(client, "environment.outside.temperature")

    assert result["unit"] is None
    assert result["display"] is None


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

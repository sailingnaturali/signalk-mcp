"""Extended TTS-protection contract for battery_state."""

import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import battery_state


def _mock_battery(soc: float, voltage: float, current: float):
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/house"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "capacity": {"stateOfCharge": {"value": soc, "timestamp": "2026-05-21T00:00:00Z"}},
                "voltage": {"value": voltage, "timestamp": "2026-05-21T00:00:00Z"},
                "current": {"value": current, "timestamp": "2026-05-21T00:00:00Z"},
            },
        )
    )


@respx.mock
async def test_battery_display_includes_spoken_units():
    """display must spell out volts/amps so TTS reads them naturally."""
    _mock_battery(0.73, 12.84, -8.2)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client, bank="house")
    assert "73" in result["display"]
    assert "volts" in result["display"]
    assert "amps" in result["display"]
    assert "discharging" in result["display"]
    await client.aclose()


@respx.mock
async def test_battery_display_says_charging_for_positive_current():
    _mock_battery(0.5, 14.1, 5.0)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client, bank="house")
    assert "charging" in result["display"]
    assert "discharging" not in result["display"]
    await client.aclose()


@respx.mock
async def test_battery_raw_values_preserved():
    """Raw fields stay alongside display so downstream tools can use them."""
    _mock_battery(0.73, 12.84, -8.2)
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client, bank="house")
    assert result["soc_fraction"] == 0.73
    assert result["voltage"] == 12.84
    assert result["current"] == -8.2
    await client.aclose()


@respx.mock
async def test_battery_display_handles_missing_values():
    """Missing fields shouldn't crash the display string."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/house"
    ).mock(return_value=httpx.Response(200, json={}))
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client, bank="house")
    assert result["soc_fraction"] is None
    assert result["display"] is None
    await client.aclose()

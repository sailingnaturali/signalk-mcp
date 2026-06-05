import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import battery_state


@respx.mock
async def test_battery_state_returns_soc_voltage_current():
    """battery_state returns SOC, voltage, current for the house bank."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/house"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "capacity": {"stateOfCharge": {"value": 0.73, "timestamp": "2026-05-14T18:00:00Z"}},
                "voltage": {"value": 12.84, "timestamp": "2026-05-14T18:00:00Z"},
                "current": {"value": -8.2, "timestamp": "2026-05-14T18:00:00Z"},
            },
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client, bank="house")

    assert result["bank"] == "house"
    assert result["soc_fraction"] == 0.73
    # display is a full spoken summary now — see test_battery_display.py for details
    assert "73 percent" in result["display"]
    assert result["voltage"] == 12.84
    assert result["current"] == -8.2


@respx.mock
async def test_battery_state_defaults_to_instance_zero():
    """battery_state uses '0' (conventional SignalK instance) as the default bank."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "capacity": {"stateOfCharge": {"value": 0.91, "timestamp": "2026-05-14T18:00:00Z"}},
                "voltage": {"value": 13.1, "timestamp": "2026-05-14T18:00:00Z"},
                "current": {"value": 2.0, "timestamp": "2026-05-14T18:00:00Z"},
            },
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await battery_state(client)

    assert result["bank"] == "0"
    assert result["soc_fraction"] == 0.91

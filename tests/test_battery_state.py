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
    assert result["state_of_charge"] == 0.73
    assert result["voltage"] == 12.84
    assert result["current"] == -8.2


@respx.mock
async def test_battery_state_defaults_to_house_bank():
    """battery_state uses 'house' as the default bank."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/electrical/batteries/house"
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

    assert result["bank"] == "house"
    assert result["state_of_charge"] == 0.91

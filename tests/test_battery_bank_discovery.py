"""battery_state must find the vessel's bank when the default instance is absent.

The bug: the default is ``bank="0"`` (the SignalK convention), but a vessel that
names its banks — ours publishes ``electrical.batteries.house`` — makes the
default return all-nulls. The agent then reports "no battery data" on a boat
that is publishing battery data. Discovery only kicks in when the CALLER did not
name a bank; an explicit bank that is absent stays absent rather than silently
answering about a different battery.
"""
import httpx
import respx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import battery_state

BASE = "http://signalk-test:3000/signalk/v1/api/vessels/self"


def _readings(soc=0.9, voltage=12.4, current=-2.7):
    return {
        "capacity": {"stateOfCharge": {"value": soc, "timestamp": "2026-08-10T00:00:00Z"}},
        "voltage": {"value": voltage, "timestamp": "2026-08-10T00:00:00Z"},
        "current": {"value": current, "timestamp": "2026-08-10T00:00:00Z"},
    }


@respx.mock
async def test_default_falls_back_to_the_only_named_bank():
    respx.get(f"{BASE}/electrical/batteries/0").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/electrical/batteries").mock(
        return_value=httpx.Response(200, json={"house": _readings()})
    )

    result = await battery_state(SignalKClient(base_url="http://signalk-test:3000"))

    assert result["bank"] == "house"
    assert result["soc_fraction"] == 0.9
    assert "90 percent" in result["display"]


@respx.mock
async def test_explicit_missing_bank_does_not_silently_answer_about_another():
    respx.get(f"{BASE}/electrical/batteries/1").mock(return_value=httpx.Response(404))
    discovery = respx.get(f"{BASE}/electrical/batteries").mock(
        return_value=httpx.Response(200, json={"house": _readings()})
    )

    result = await battery_state(SignalKClient(base_url="http://signalk-test:3000"), bank="1")

    assert result["bank"] == "1"
    assert result["soc_fraction"] is None
    assert not discovery.called, "an explicitly named bank must not trigger discovery"


@respx.mock
async def test_prefers_house_when_several_banks_exist():
    respx.get(f"{BASE}/electrical/batteries/0").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/electrical/batteries").mock(
        return_value=httpx.Response(
            200, json={"start": _readings(soc=1.0), "house": _readings(soc=0.62)}
        )
    )

    result = await battery_state(SignalKClient(base_url="http://signalk-test:3000"))

    assert result["bank"] == "house"
    assert result["soc_fraction"] == 0.62


@respx.mock
async def test_ambiguous_banks_are_reported_not_guessed():
    """Two banks, neither named house: guessing could answer about the start
    battery when the crew meant the house bank. Name the options instead."""
    respx.get(f"{BASE}/electrical/batteries/0").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/electrical/batteries").mock(
        return_value=httpx.Response(200, json={"bank1": _readings(), "bank2": _readings()})
    )

    result = await battery_state(SignalKClient(base_url="http://signalk-test:3000"))

    assert result["soc_fraction"] is None
    assert sorted(result["available_banks"]) == ["bank1", "bank2"]


@respx.mock
async def test_no_batteries_at_all_is_not_a_crash():
    respx.get(f"{BASE}/electrical/batteries/0").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/electrical/batteries").mock(return_value=httpx.Response(404))

    result = await battery_state(SignalKClient(base_url="http://signalk-test:3000"))

    assert result["soc_fraction"] is None
    assert result["display"] is None

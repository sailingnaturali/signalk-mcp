import httpx
import respx

from signalk_mcp.client import SignalKClient

NOTIF_URL = "http://signalk-test:3000/signalk/v1/api/vessels/self/notifications"


def _client() -> SignalKClient:
    return SignalKClient(base_url="http://signalk-test:3000")


@respx.mock
async def test_get_notifications_returns_subtree():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(200, json={"propulsion": {"0": {}}}))
    tree = await _client().get_notifications()
    assert tree == {"propulsion": {"0": {}}}


@respx.mock
async def test_get_notifications_404_is_empty():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(404))
    assert await _client().get_notifications() == {}


from signalk_mcp.tools import get_active_alarms

NOTIF_TREE = {
    "propulsion": {"0": {"temperature": {"value": {
        "state": "warn", "message": "Motor temp high", "timestamp": "2026-06-04T00:00:00Z"}}}},
    "electrical": {"batteries": {"house": {"voltage": {"value": {
        "state": "alarm", "message": "Low voltage"}}}}},
    "tanks": {"freshWater": {"0": {"currentLevel": {"value": {
        "state": "normal", "message": "ok"}}}}},
    "environment": {"depth": {"belowKeel": {"value": None}}},
}


@respx.mock
async def test_get_active_alarms_filters_and_strips_prefix():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(200, json=NOTIF_TREE))
    result = await get_active_alarms(_client())
    paths = {a["path"] for a in result["alarms"]}
    assert paths == {"propulsion.0.temperature", "electrical.batteries.house.voltage"}
    assert "tanks.freshWater.0.currentLevel" not in paths
    assert "environment.depth.belowKeel" not in paths


@respx.mock
async def test_get_active_alarms_sorted_most_severe_first():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(200, json=NOTIF_TREE))
    result = await get_active_alarms(_client())
    assert [a["state"] for a in result["alarms"]] == ["alarm", "warn"]
    first = result["alarms"][0]
    assert first["path"] == "electrical.batteries.house.voltage"
    assert first["message"] == "Low voltage"


@respx.mock
async def test_get_active_alarms_empty_when_all_clear():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(200, json={}))
    assert await get_active_alarms(_client()) == {"alarms": []}


@respx.mock
async def test_get_active_alarms_carries_timestamp():
    respx.get(NOTIF_URL).mock(return_value=httpx.Response(200, json=NOTIF_TREE))
    result = await get_active_alarms(_client())
    warn = next(a for a in result["alarms"] if a["path"] == "propulsion.0.temperature")
    assert warn["timestamp"] == "2026-06-04T00:00:00Z"

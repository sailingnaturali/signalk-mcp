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

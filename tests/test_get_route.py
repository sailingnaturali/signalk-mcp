import pytest
import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import get_route


@respx.mock
async def test_get_route_returns_active_route_waypoints():
    """get_route returns the current active route's waypoints in order."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "href": {"value": "/resources/routes/r-1"},
                "startTime": {"value": "2026-05-14T17:00:00Z"},
            },
        )
    )
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/resources/routes/r-1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "Victoria → Pender Harbour",
                "feature": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-123.36, 48.42],
                            [-123.50, 48.55],
                            [-124.00, 49.00],
                        ],
                    }
                },
            },
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_route(client)

    assert result["name"] == "Victoria → Pender Harbour"
    assert len(result["waypoints"]) == 3
    assert result["waypoints"][0] == {"longitude": -123.36, "latitude": 48.42}
    assert result["start_time"] == "2026-05-14T17:00:00Z"


@respx.mock
async def test_get_route_raises_when_no_active_route():
    """get_route raises ValueError when no route is active."""
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(return_value=httpx.Response(200, json={}))

    client = SignalKClient(base_url="http://signalk-test:3000")

    with pytest.raises(ValueError, match="No active route"):
        await get_route(client)


@respx.mock
async def test_get_route_rejects_traversal_shaped_href():
    # The href comes from the vessel's own server, but it reaches a URL sink —
    # validate like every other segment (fleet conventions R5).
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(return_value=httpx.Response(
        200, json={"href": {"value": "/resources/../../skServer/secrets"}}))
    client = SignalKClient("http://signalk-test:3000")
    with pytest.raises(ValueError, match="href"):
        await get_route(client)
    await client.aclose()


@respx.mock
async def test_get_route_rejects_protocol_relative_href():
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(return_value=httpx.Response(
        200, json={"href": {"value": "//evil.example/resources/routes/r-1"}}))
    client = SignalKClient("http://signalk-test:3000")
    with pytest.raises(ValueError, match="href"):
        await get_route(client)
    await client.aclose()


@respx.mock
async def test_get_route_stale_href_returns_empty_route_not_error():
    # 404 = absent, the client's own contract — a stale href must not raise.
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(return_value=httpx.Response(
        200, json={"href": {"value": "/resources/routes/deleted"}}))
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/resources/routes/deleted"
    ).mock(return_value=httpx.Response(404))
    client = SignalKClient("http://signalk-test:3000")
    out = await get_route(client)
    assert out["waypoints"] == []
    await client.aclose()

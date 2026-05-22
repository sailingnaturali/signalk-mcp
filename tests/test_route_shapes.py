"""get_route must handle GeoJSON edge cases the original parser crashed on."""

import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import get_route


def _mock_active_route_href(href: str = "/resources/routes/r-1"):
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"href": {"value": href}, "startTime": {"value": "2026-05-21T00:00:00Z"}},
        )
    )


@respx.mock
async def test_get_route_tolerates_elevation_in_coordinates():
    """GeoJSON allows [lon, lat, elev]; we must drop the elevation, not crash."""
    _mock_active_route_href()
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/resources/routes/r-1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "With elevation",
                "feature": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-123.36, 48.42, 0.0],
                            [-123.50, 48.55, 10.0],
                        ],
                    }
                },
            },
        )
    )
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_route(client)
    assert len(result["waypoints"]) == 2
    assert result["waypoints"][0] == {"longitude": -123.36, "latitude": 48.42}
    await client.aclose()


@respx.mock
async def test_get_route_handles_feature_collection():
    """Some SignalK route resources use FeatureCollection with `features[0]`."""
    _mock_active_route_href()
    respx.get(
        "http://signalk-test:3000/signalk/v1/api/resources/routes/r-1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "FC route",
                "feature": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[-1.0, 50.0], [-1.1, 50.1]],
                            }
                        }
                    ],
                },
            },
        )
    )
    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await get_route(client)
    assert len(result["waypoints"]) == 2
    await client.aclose()

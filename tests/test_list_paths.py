"""Tests for list_paths — SignalK tree discovery so agents stop guessing paths."""

import httpx
import respx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import list_paths

SELF_URL = "http://signalk-test:3000/signalk/v1/api/vessels/self/"

# A realistic slice of a SignalK self tree: nested branches, leaves with `value`
# + `meta`, a leaf with no meta (position), and a plain-string `uuid` that is NOT
# a value-node and must be ignored.
TREE = {
    "uuid": "urn:mrn:signalk:uuid:abc",
    "navigation": {
        "speedThroughWater": {
            "value": 2.6,
            "meta": {"units": "m/s", "description": "Vessel speed through water"},
            "$source": "nmea.II",
            "timestamp": "2026-06-03T00:00:00Z",
        },
        "position": {
            "value": {"latitude": 48.4, "longitude": -123.3},
            "$source": "nmea.GP",
        },
    },
    "environment": {
        "depth": {
            "belowTransducer": {
                "value": 27.1,
                "meta": {"units": "m", "description": "Depth below Transducer"},
            },
        },
    },
}


def _client() -> SignalKClient:
    return SignalKClient(base_url="http://signalk-test:3000")


@respx.mock
async def test_list_paths_flattens_tree_with_meta():
    respx.get(SELF_URL).mock(return_value=httpx.Response(200, json=TREE))

    result = await list_paths(_client())
    by_path = {p["path"]: p for p in result["paths"]}

    assert result["count"] == 3
    assert by_path["environment.depth.belowTransducer"]["units"] == "m"
    assert by_path["environment.depth.belowTransducer"]["description"] == "Depth below Transducer"
    assert "navigation.speedThroughWater" in by_path
    assert "uuid" not in by_path  # plain string, not a value-node


@respx.mock
async def test_list_paths_sorted():
    respx.get(SELF_URL).mock(return_value=httpx.Response(200, json=TREE))

    result = await list_paths(_client())
    names = [p["path"] for p in result["paths"]]
    assert names == sorted(names)


@respx.mock
async def test_list_paths_prefix_filter():
    respx.get(SELF_URL).mock(return_value=httpx.Response(200, json=TREE))

    result = await list_paths(_client(), prefix="environment")
    names = {p["path"] for p in result["paths"]}
    assert names == {"environment.depth.belowTransducer"}


@respx.mock
async def test_list_paths_leaf_without_meta_yields_none():
    respx.get(SELF_URL).mock(return_value=httpx.Response(200, json=TREE))

    result = await list_paths(_client())
    pos = next(p for p in result["paths"] if p["path"] == "navigation.position")
    assert pos["units"] is None
    assert pos["description"] is None


@respx.mock
async def test_list_paths_empty_on_404():
    """No self vessel / empty tree is a normal 'nothing here', not an error."""
    respx.get(SELF_URL).mock(return_value=httpx.Response(404))

    result = await list_paths(_client())
    assert result == {"paths": [], "count": 0}

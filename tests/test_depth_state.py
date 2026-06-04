import respx
import httpx

from signalk_mcp.client import SignalKClient
from signalk_mcp.tools import depth_state

_URL = "http://signalk-test:3000/signalk/v1/api/vessels/self/environment/depth"


@respx.mock
async def test_depth_state_leads_with_under_keel_clearance():
    """With belowKeel present, depth_state reports under-keel clearance first.

    This is the "how's our depth?" / "how close are we to running aground?"
    answer — belowKeel IS the clearance, no draft math needed.
    """
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "belowKeel": {"value": 4.87, "timestamp": "2026-06-04T01:55:00Z"},
                "belowSurface": {"value": 6.24, "timestamp": "2026-06-04T01:55:00Z"},
                "belowTransducer": {"value": 5.99, "timestamp": "2026-06-04T01:55:00Z"},
                "transducerToKeel": {"value": -1.12},
            },
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await depth_state(client)

    assert result["below_keel_m"] == 4.87
    assert result["below_surface_m"] == 6.24
    assert result["below_transducer_m"] == 5.99
    # Spoken summary leads with under-keel clearance.
    assert result["display"].startswith("4.9 metres under the keel")
    assert "6.2 metres of water" in result["display"]
    assert result["timestamp"] == "2026-06-04T01:55:00Z"


@respx.mock
async def test_depth_state_without_keel_offset_says_unavailable():
    """A DBT-only feed (no belowKeel) must not be reported as under-keel
    clearance — say it's unavailable rather than imply false safety margin."""
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"belowTransducer": {"value": 5.99, "timestamp": "2026-06-04T01:55:00Z"}},
        )
    )

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await depth_state(client)

    assert result["below_keel_m"] is None
    assert result["below_transducer_m"] == 5.99
    assert "under-keel clearance unavailable" in result["display"]
    assert "6.0 metres below the transducer" in result["display"]


@respx.mock
async def test_depth_state_no_data_returns_none_display():
    """No depth published (404) → null values and no fabricated display."""
    respx.get(_URL).mock(return_value=httpx.Response(404))

    client = SignalKClient(base_url="http://signalk-test:3000")
    result = await depth_state(client)

    assert result["below_keel_m"] is None
    assert result["below_surface_m"] is None
    assert result["below_transducer_m"] is None
    assert result["display"] is None

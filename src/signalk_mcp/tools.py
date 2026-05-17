"""MCP tool implementations for signalk-mcp.

Each tool is an async function that returns a JSON-serializable dict
matching the MCP tool response schema.
"""

from __future__ import annotations

import httpx

from signalk_mcp.client import SignalKClient


async def get_route(client: SignalKClient) -> dict:
    """Return the currently active route with waypoints in order.

    Returns:
        Dict with keys ``name``, ``waypoints`` (list of {longitude, latitude}),
        and ``start_time``.

    Raises:
        ValueError: if no active route is set.
    """
    active = await client.get_value("navigation.courseGreatCircle.activeRoute")
    href_obj = active.get("href") or {}
    href = href_obj.get("value")
    if not href:
        raise ValueError("No active route set on SignalK")

    route_url = client.base_url + "/signalk/v1/api" + href
    async with httpx.AsyncClient(timeout=5.0) as http:
        resp = await http.get(route_url)
        resp.raise_for_status()
        route = resp.json()

    coords = (
        route.get("feature", {})
        .get("geometry", {})
        .get("coordinates", [])
    )
    waypoints = [{"longitude": lon, "latitude": lat} for lon, lat in coords]

    return {
        "name": route.get("name", "(unnamed)"),
        "waypoints": waypoints,
        "start_time": (active.get("startTime") or {}).get("value"),
    }


async def battery_state(client: SignalKClient, bank: str = "house") -> dict:
    """Return state of charge, voltage, current for a battery bank.

    Args:
        client: An open SignalKClient.
        bank: Battery bank name (default ``house``).

    Returns:
        Dict with keys ``bank``, ``state_of_charge`` (0-1), ``voltage`` (V),
        ``current`` (A, negative = discharging), ``timestamp``.
    """
    raw = await client.get_value(f"electrical.batteries.{bank}")
    soc_obj = raw.get("capacity", {}).get("stateOfCharge", {}) or {}
    voltage_obj = raw.get("voltage", {}) or {}
    current_obj = raw.get("current", {}) or {}

    return {
        "bank": bank,
        "state_of_charge": soc_obj.get("value"),
        "voltage": voltage_obj.get("value"),
        "current": current_obj.get("value"),
        "timestamp": soc_obj.get("timestamp") or voltage_obj.get("timestamp"),
    }


async def read_sensor(client: SignalKClient, path: str) -> dict:
    """Read a SignalK path and return its current value + timestamp.

    Args:
        client: An open SignalKClient.
        path: SignalK dotted path (e.g. ``environment.wind.speedTrue``).

    Returns:
        Dict with keys ``path``, ``value``, ``timestamp``.
    """
    raw = await client.get_value(path)
    return {
        "path": path,
        "value": raw.get("value"),
        "timestamp": raw.get("timestamp"),
    }

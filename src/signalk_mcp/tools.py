"""MCP tool implementations for signalk-mcp.

Each tool is an async function that returns a JSON-serializable dict
matching the MCP tool response schema.
"""

from __future__ import annotations

import math

from signalk_mcp.client import SignalKClient


def _degrees_to_compass(deg: float) -> str:
    """Return 16-point compass rose label for a true bearing."""
    points = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    idx = round(deg / 22.5) % 16
    return points[idx]


def _convert(path: str, value: object) -> tuple[str | None, str | None]:
    """Return (display_string, unit) for a known SignalK path, else (None, None).

    SignalK always stores values in SI units:
      - speeds in m/s → knots
      - angles/headings/courses in radians → degrees
      - pressure in Pa → hPa
      - temperature in K → °C
      - depth in m → m (no conversion, kept for completeness)
    """
    if not isinstance(value, (int, float)):
        return None, None

    tail = path.rsplit(".", 1)[-1]

    # Speed: m/s → knots
    _speed_keys = {"speedTrue", "speedOverGround", "speedThroughWater", "speedApparent"}
    if tail in _speed_keys:
        kts = value * 1.94384
        return f"{kts:.1f} kts", "kts"

    # Angles, headings, courses: radians → degrees + compass label
    _bearing_keys = {
        "headingTrue", "headingMagnetic",
        "courseOverGroundTrue", "courseOverGroundMagnetic",
    }
    _wind_angle_keys = {"angleTrueWater", "angleApparentWater"}
    if tail in _bearing_keys:
        deg = math.degrees(value) % 360
        return f"{deg:.1f}°T ({_degrees_to_compass(deg)})", "°T"
    if tail in _wind_angle_keys:
        deg = math.degrees(value) % 360
        compass = _degrees_to_compass(deg)
        return f"{deg:.1f}°T ({compass} wind)", "°T"
    if tail == "magneticVariation":
        deg = math.degrees(value)
        return f"{deg:.1f}°", "°"

    # Pressure: Pa → hPa
    if tail == "pressure":
        hpa = value / 100.0
        return f"{hpa:.1f} hPa", "hPa"

    # Temperature: K → °C
    if tail == "temperature":
        celsius = value - 273.15
        return f"{celsius:.1f}°C", "°C"

    # Depth: already metres
    if tail in {"belowKeel", "belowSurface", "belowTransducer"}:
        return f"{value:.1f} m", "m"

    return None, None


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

    route = await client.get_resource(href)

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
        Dict with keys ``path``, ``value`` (raw SI), ``display`` (human-readable
        with units, or None), ``unit`` (unit string, or None), ``timestamp``.
    """
    raw = await client.get_value(path)
    value = raw.get("value")
    display, unit = _convert(path, value)
    return {
        "path": path,
        "value": value,
        "display": display,
        "unit": unit,
        "timestamp": raw.get("timestamp"),
    }

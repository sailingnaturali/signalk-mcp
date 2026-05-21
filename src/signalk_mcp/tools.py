"""MCP tool implementations for signalk-mcp.

Each tool is an async function that returns a JSON-serializable dict
matching the MCP tool response schema.
"""

from __future__ import annotations

import math
import zoneinfo
from datetime import datetime, timezone

from timezonefinder import TimezoneFinder

from signalk_mcp.client import SignalKClient

_tf = TimezoneFinder()


def _degrees_to_compass(deg: float) -> str:
    """Return 16-point compass rose label for a true bearing, spoken form."""
    points = [
        "North", "North-North-East", "North-East", "East-North-East",
        "East", "East-South-East", "South-East", "South-South-East",
        "South", "South-South-West", "South-West", "West-South-West",
        "West", "West-North-West", "North-West", "North-North-West",
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
    if path == "navigation.position" and isinstance(value, dict):
        lat = value.get("latitude")
        lon = value.get("longitude")
        if lat is None or lon is None:
            return None, None
        lat_dir = "North" if lat >= 0 else "South"
        lon_dir = "East" if lon >= 0 else "West"
        return f"{abs(lat):.4f} {lat_dir}, {abs(lon):.4f} {lon_dir}", "°"

    if not isinstance(value, (int, float)):
        return None, None

    tail = path.rsplit(".", 1)[-1]

    # Speed: m/s → knots
    _speed_keys = {"speedTrue", "speedOverGround", "speedThroughWater", "speedApparent"}
    if tail in _speed_keys:
        kts = value * 1.94384
        return f"{kts:.1f} knots", "knots"

    # Angles, headings, courses: radians → degrees + compass label
    _bearing_keys = {
        "headingTrue", "headingMagnetic",
        "courseOverGroundTrue", "courseOverGroundMagnetic",
    }
    _wind_angle_keys = {"angleTrueWater", "angleApparentWater"}
    if tail in _bearing_keys:
        deg = math.degrees(value) % 360
        return f"{deg:.1f}° ({_degrees_to_compass(deg)})", "°"
    if tail in _wind_angle_keys:
        deg = math.degrees(value) % 360
        compass = _degrees_to_compass(deg)
        return f"{deg:.1f}° ({compass} wind)", "°"
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


async def get_local_time(client: SignalKClient) -> dict:
    """Return current time localized to the vessel's GPS position.

    Args:
        client: An open SignalKClient.

    Returns:
        Dict with keys ``utc`` (ISO string), ``local`` (ISO string),
        ``timezone`` (IANA name), ``display`` (e.g. ``"11:54"``).
        Falls back to UTC if position is unavailable.
    """
    now_utc = datetime.now(timezone.utc)

    try:
        pos_raw = await client.get_value("navigation.position")
        pos = pos_raw.get("value") or {}
        lat = pos.get("latitude")
        lon = pos.get("longitude")
    except Exception:
        lat = lon = None

    if lat is not None and lon is not None:
        tz_name = _tf.timezone_at(lat=lat, lng=lon)
        if tz_name:
            tz = zoneinfo.ZoneInfo(tz_name)
            now_local = now_utc.astimezone(tz)
            return {
                "iana_timezone": tz_name,
                "display": now_local.strftime("%H:%M"),
            }

    return {
        "iana_timezone": "UTC",
        "display": now_utc.strftime("%H:%M"),
    }


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

    soc = soc_obj.get("value")
    display = f"{soc * 100:.0f}%" if soc is not None else None
    return {
        "bank": bank,
        "soc_fraction": soc,
        "display": display,
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
        "value": None if isinstance(value, dict) else value,
        "display": display,
        "unit": unit,
        "timestamp": raw.get("timestamp"),
    }

"""MCP tool implementations for signalk-mcp.

Each tool is an async function that returns a JSON-serializable dict
matching the contract in SPEC.md.
"""

from __future__ import annotations

import logging
import math
import zoneinfo
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from signalk_mcp.client import SignalKClient, validate_path_segment

if TYPE_CHECKING:
    from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

_tf: "TimezoneFinder | None" = None


def _get_timezone_finder() -> "TimezoneFinder":
    """Lazy-init TimezoneFinder — it loads ~50MB of shapefile data."""
    global _tf
    if _tf is None:
        from timezonefinder import TimezoneFinder
        _tf = TimezoneFinder()
    return _tf


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


# --- conversion table key sets ---
_SPEED_KEYS = {"speedTrue", "speedOverGround", "speedThroughWater", "speedApparent"}
_BEARING_KEYS = {
    "headingTrue", "headingMagnetic",
    "courseOverGroundTrue", "courseOverGroundMagnetic",
    "directionTrue", "directionMagnetic",
}
_RELATIVE_WIND_KEYS = {"angleTrueWater", "angleTrueGround", "angleApparent"}
_DEPTH_KEYS = {"belowKeel", "belowSurface", "belowTransducer"}


def _convert(path: str, value: object) -> tuple[str | None, str | None]:
    """Return (display_string, unit) for a known SignalK path, else (None, None).

    SignalK always stores values in SI units. See SPEC.md for the full table.
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

    if tail in _SPEED_KEYS:
        kts = value * 1.94384
        return f"{kts:.1f} knots", "knots"

    if tail in _BEARING_KEYS:
        deg = math.degrees(value) % 360
        return f"{deg:.1f}° ({_degrees_to_compass(deg)})", "°"

    if tail in _RELATIVE_WIND_KEYS:
        # Normalize to (-180, 180] so wraparound (e.g. 315° from a [0, 2π)
        # source) is reported as 45° to port rather than off the wrong side.
        deg = ((math.degrees(value) + 180) % 360) - 180
        side = "starboard" if deg >= 0 else "port"
        return f"{abs(deg):.0f}° off the {side} bow", "°"

    if tail == "magneticVariation":
        deg = math.degrees(value)
        side = "East" if deg >= 0 else "West"
        return f"{abs(deg):.1f}° {side}", "°"

    if tail == "pressure":
        hpa = value / 100.0
        return f"{hpa:.1f} hPa", "hPa"

    if tail == "temperature":
        celsius = value - 273.15
        return f"{celsius:.1f}°C", "°C"

    if tail in _DEPTH_KEYS:
        return f"{value:.1f} m", "m"

    return None, None


async def get_local_time(client: SignalKClient) -> dict:
    """Return current time localized to the vessel's GPS position.

    Falls back to UTC if position is unavailable. Network/auth errors are
    logged and treated the same as missing position.
    """
    now_utc = datetime.now(timezone.utc)

    lat = lon = None
    try:
        pos_raw = await client.get_value("navigation.position")
        pos = pos_raw.get("value") or {}
        lat = pos.get("latitude")
        lon = pos.get("longitude")
    except Exception as exc:
        logger.warning("get_local_time: failed to fetch position (%s); falling back to UTC", exc)

    if lat is not None and lon is not None:
        tz_name = _get_timezone_finder().timezone_at(lat=lat, lng=lon)
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


def _extract_coordinates(route: dict) -> list:
    """Pull coordinates out of either Feature or FeatureCollection-shaped routes."""
    feature = route.get("feature", {}) or {}
    if feature.get("type") == "FeatureCollection":
        features = feature.get("features") or []
        if features:
            return features[0].get("geometry", {}).get("coordinates", []) or []
        return []
    return feature.get("geometry", {}).get("coordinates", []) or []


async def get_route(client: SignalKClient) -> dict:
    """Return the currently active route with waypoints in order."""
    active = await client.get_value("navigation.courseGreatCircle.activeRoute")
    href_obj = active.get("href") or {}
    href = href_obj.get("value")
    if not href:
        raise ValueError("No active route set on SignalK")

    route = await client.get_resource(href)
    coords = _extract_coordinates(route)

    # GeoJSON coords may be [lon, lat] or [lon, lat, elev]; take first two.
    waypoints = [
        {"longitude": c[0], "latitude": c[1]}
        for c in coords
        if isinstance(c, (list, tuple)) and len(c) >= 2
    ]

    return {
        "name": route.get("name", "(unnamed)"),
        "waypoints": waypoints,
        "start_time": (active.get("startTime") or {}).get("value"),
    }


def _battery_display(soc: float | None, voltage: float | None, current: float | None) -> str | None:
    """Compose a TTS-safe summary of the battery state.

    Returns None when no fields are present (e.g. unknown bank).
    """
    parts: list[str] = []
    if soc is not None:
        parts.append(f"{soc * 100:.0f} percent")
    if voltage is not None:
        parts.append(f"{voltage:.1f} volts")
    if current is not None:
        direction = "charging" if current > 0 else "discharging"
        parts.append(f"{abs(current):.1f} amps {direction}")
    return ", ".join(parts) if parts else None


async def battery_state(client: SignalKClient, bank: str = "house") -> dict:
    """Return state of charge, voltage, current for a battery bank."""
    validate_path_segment(bank, "bank")
    raw = await client.get_value(f"electrical.batteries.{bank}")
    soc_obj = raw.get("capacity", {}).get("stateOfCharge", {}) or {}
    voltage_obj = raw.get("voltage", {}) or {}
    current_obj = raw.get("current", {}) or {}

    soc = soc_obj.get("value")
    voltage = voltage_obj.get("value")
    current = current_obj.get("value")
    return {
        "bank": bank,
        "soc_fraction": soc,
        "voltage": voltage,
        "current": current,
        "display": _battery_display(soc, voltage, current),
        "timestamp": soc_obj.get("timestamp") or voltage_obj.get("timestamp") or current_obj.get("timestamp"),
    }


async def read_sensor(client: SignalKClient, path: str) -> dict:
    """Read a SignalK path and return its current value + display."""
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

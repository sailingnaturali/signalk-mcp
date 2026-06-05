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


async def battery_state(client: SignalKClient, bank: str = "0") -> dict:
    """Return state of charge, voltage, current for a battery bank.

    ``bank`` is the SignalK instance key under ``electrical.batteries`` —
    conventionally numeric ("0"), but named banks ("house") work too.
    """
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


def _depth_display(
    below_keel: float | None,
    below_surface: float | None,
    below_transducer: float | None,
) -> str | None:
    """Compose a TTS-safe depth summary that leads with under-keel clearance.

    belowKeel IS the clearance under the hull — the answer to "how's our depth?"
    and "how close are we to running aground?", no draft arithmetic required.
    When it's absent (e.g. a DBT-only sounder with no keel offset configured)
    we say so rather than passing a transducer reading off as keel clearance.
    """
    if below_keel is not None:
        s = f"{below_keel:.1f} metres under the keel"
        if below_surface is not None:
            # "total depth" — surface to seabed. Spell it out: a bare
            # "N metres of water" got narrated as "water above us" by an 8B.
            s += f", {below_surface:.1f} metres total depth"
        return s
    if below_surface is not None:
        return (
            f"{below_surface:.1f} metres total depth (surface to seabed); "
            "under-keel clearance unavailable"
        )
    if below_transducer is not None:
        return (
            f"{below_transducer:.1f} metres below the transducer; "
            "under-keel clearance unavailable"
        )
    return None


async def depth_state(client: SignalKClient) -> dict:
    """Return water depth with under-keel clearance front and centre.

    Reads the ``environment.depth`` subtree and leads with ``belowKeel`` (the
    clearance under the hull) so an agent never has to guess paths or do draft
    math to answer depth / grounding questions. Falls back to surface- or
    transducer-referenced depth, clearly labelled, when keel clearance isn't
    published.
    """
    raw = await client.get_value("environment.depth")
    below_keel_obj = raw.get("belowKeel") or {}
    below_surface_obj = raw.get("belowSurface") or {}
    below_transducer_obj = raw.get("belowTransducer") or {}

    below_keel = below_keel_obj.get("value")
    below_surface = below_surface_obj.get("value")
    below_transducer = below_transducer_obj.get("value")
    return {
        "below_keel_m": below_keel,
        "below_surface_m": below_surface,
        "below_transducer_m": below_transducer,
        "display": _depth_display(below_keel, below_surface, below_transducer),
        "timestamp": (
            below_keel_obj.get("timestamp")
            or below_surface_obj.get("timestamp")
            or below_transducer_obj.get("timestamp")
        ),
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


# Keys inside a SignalK node that are metadata, not child paths.
_NON_PATH_KEYS = {"meta", "$source", "source", "timestamp", "pgn", "sentence"}

_ALARM_SEVERITY = {"emergency": 0, "alarm": 1, "warn": 2, "alert": 3}
_INACTIVE_STATES = {"normal", "nominal"}


def _flatten_alarms(node: object, prefix: str = "") -> list[dict]:
    """Walk a SignalK notifications subtree, emitting one row per ACTIVE alarm.

    A leaf is a dict with a ``value`` key; the notification payload is that
    ``value`` (a dict with ``state``/``message``/``timestamp``). A null value is
    a cleared alarm. States ``normal``/``nominal`` are not active. ``prefix`` is
    already free of the ``notifications.`` prefix because the caller fetched the
    subtree endpoint.
    """
    if not isinstance(node, dict):
        return []
    if "value" in node:
        val = node.get("value")
        if not isinstance(val, dict):
            return []
        state = val.get("state")
        if state is None or state in _INACTIVE_STATES:
            return []
        return [{
            "path": prefix,
            "state": state,
            "message": val.get("message"),
            "timestamp": val.get("timestamp") or node.get("timestamp"),
        }]
    rows: list[dict] = []
    for key, child in node.items():
        if key in _NON_PATH_KEYS:
            continue
        child_prefix = f"{prefix}.{key}" if prefix else key
        rows.extend(_flatten_alarms(child, child_prefix))
    return rows


async def get_active_alarms(client: SignalKClient) -> dict:
    """Active SignalK notifications (anything not ``normal``), worst severity first.

    Returns ``{alarms: [{path, state, message, timestamp}]}`` with ``path`` as the
    monitored SignalK path (no ``notifications.`` prefix) so it feeds straight into
    vessel-knowledge's ``explain_notification``. Empty list means all clear.
    """
    tree = await client.get_notifications()
    rows = _flatten_alarms(tree)
    rows.sort(key=lambda r: _ALARM_SEVERITY.get(r["state"], 99))
    return {"alarms": rows}


def _flatten_paths(node: object, prefix: str = "") -> list[dict]:
    """Walk a SignalK tree, emitting one row per value-bearing leaf.

    A dict containing a ``value`` key is a leaf path (don't recurse into it);
    anything else is a branch we recurse into, skipping metadata keys. ``units``
    and ``description`` come from the leaf's ``meta`` (``None`` when absent).
    """
    if not isinstance(node, dict):
        return []
    if "value" in node:
        meta = node.get("meta") or {}
        return [{"path": prefix, "units": meta.get("units"), "description": meta.get("description")}]
    rows: list[dict] = []
    for key, child in node.items():
        if key in _NON_PATH_KEYS:
            continue
        child_prefix = f"{prefix}.{key}" if prefix else key
        rows.extend(_flatten_paths(child, child_prefix))
    return rows


async def list_paths(client: SignalKClient, prefix: str | None = None) -> dict:
    """List the SignalK paths this vessel actually publishes, so an agent can
    discover the right path (e.g. ``environment.depth.belowTransducer``) instead
    of guessing. Returns ``{paths: [{path, units, description}], count}`` sorted
    by path. ``prefix`` filters to paths starting with that string.
    """
    tree = await client.get_self_tree()
    rows = _flatten_paths(tree)
    if prefix:
        rows = [r for r in rows if r["path"].startswith(prefix)]
    rows.sort(key=lambda r: r["path"])
    return {"paths": rows, "count": len(rows)}

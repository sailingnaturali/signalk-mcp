# signalk-mcp specification

This document captures the design contracts the `signalk-mcp` server upholds.
It is the source of truth for what tools may return and what they may not.

## Scope

`signalk-mcp` exposes a SignalK server as an MCP tool surface for AI agents
(voice-first or text). It is read-only over REST in v0.1; WebSocket
subscriptions and authenticated write paths are out of scope until v0.2+.

## Response contract

Every tool returns a JSON-serializable dict. All keys must satisfy these
invariants:

1. **`display`** — a string the agent may speak verbatim. TTS-safe means:
   spelled-out units (`"knots"`, not `"kn"`), spelled-out compass points
   (`"North-East"`, not `"NE"`), no ISO timestamps, no bare lat/lon, no
   unit suffixes the agent might pronounce as letters (`°T`, `kn`).
2. **`value`** — the raw SI scalar for downstream programmatic use.
   - Scalar SignalK paths (m/s, radians, Pa, K, V, A, fraction) return the
     raw number.
   - Structured paths (position, waypoint lists) return `None` here; the
     structured payload is exposed under a tool-specific key
     (e.g. `waypoints`).
3. **`unit`** — the unit of `value` as a short string (`"knots"`, `"°"`,
   `"V"`, `"A"`, `"hPa"`, `"°C"`, `"m"`, `null`). The unit applies to the
   *converted* display, not the raw SI input.
4. **`timestamp`** — pass-through of SignalK's timestamp as an ISO 8601
   string, or `null`. Not currently humanized.

### TTS-protection rule

Any field that can carry a number the agent might speak must have a
companion `display` string. Specifically:

- Position: `display` only; no raw lat/lon at top level.
- Battery voltage/current/SOC: each gets a spoken display (`"12.8 volts"`,
  `"8.2 amps discharging"`, `"73 percent"`). Raw values stay in their own
  keys for downstream use.
- Sensor readings: `display` formatted by `_convert`. Paths with no
  recognized conversion get `display=None, unit=None` — the agent is
  expected to handle this case (e.g. ask for clarification) rather than
  speak the raw number.

Timestamps are intentionally left raw for v0.1; agents speak them poorly,
but humanizing them is deferred to v0.2.

## Input validation

Path-like arguments (`read_sensor.path`, `battery_state.bank`) are
interpolated into the SignalK URL. They must match `^[A-Za-z0-9._-]+$`.
Anything outside that set raises `ValueError` before any HTTP call. This
prevents path traversal through agent input and crashes from malformed
strings.

## Client lifecycle

A single `SignalKClient` (one `httpx.AsyncClient` with keep-alive) is
created at server startup and reused for the lifetime of the process.
Tool handlers must not create their own clients. The client is closed
once when the stdio transport exits.

## Tools

### `read_sensor(path: str)`
- `path` must be a dotted SignalK path under `vessels/self/`.
- Returns `{path, value, display, unit, timestamp}`.
- For `navigation.position`, `value` is `None` and `display` carries the
  full cardinal-name lat/lon.

### `get_route()`
- Returns `{name, waypoints, start_time}` for the currently active route.
- `waypoints` is a list of `{longitude, latitude}` dicts in order.
- Coordinate triples with elevation (`[lon, lat, elev]`) are tolerated;
  the elevation is dropped.
- Both `feature` (single Feature) and `features[0]` (FeatureCollection)
  shapes are accepted.
- Raises `ValueError` if no active route is set.

### `battery_state(bank: str = "house")`
- Returns `{bank, soc_fraction, voltage, current, display, timestamp}`.
- `display` is a spoken summary (e.g. `"73 percent, 12.8 volts, 8.2 amps
  discharging"`).
- `bank` must match the path-validation rule.

### `get_local_time()`
- Returns `{iana_timezone, display}` where `display` is `HH:MM` in the
  vessel's local time, or UTC if position is unavailable.
- A network/auth failure when fetching position falls back to UTC and
  logs a warning. A missing position field (no GPS fix) falls back
  silently — that is normal at the dock.

## Unit conversions

| SignalK tail                                    | SI in | Display unit       |
|-------------------------------------------------|-------|---------------------|
| `speedTrue`, `speedOverGround`, `speedThroughWater`, `speedApparent` | m/s   | knots               |
| `headingTrue`, `headingMagnetic`, `courseOverGroundTrue`, `courseOverGroundMagnetic`, `directionTrue`, `directionMagnetic` | rad   | ° + compass label   |
| `angleTrueWater`, `angleTrueGround`, `angleApparent`                                       | rad   | ° + port/starboard  |
| `magneticVariation`                             | rad   | ° + East/West       |
| `pressure`                                      | Pa    | hPa                 |
| `temperature`                                   | K     | °C                  |
| `belowKeel`, `belowSurface`, `belowTransducer`  | m     | m (pass-through)    |

Relative wind angles (`angle*`) are signed in SignalK (positive =
starboard, negative = port). The display preserves this: e.g.
`"45° off the starboard bow"`. Bearings/directions are compass-frame
0–360°.

## Out of scope (v0.1)

- WebSocket subscriptions / streaming updates.
- SignalK authentication tokens (read-only public data only).
- Write paths (e.g. `PUT` to set values).
- Humanized timestamps.
- Multi-vessel — `vessels/self` only.

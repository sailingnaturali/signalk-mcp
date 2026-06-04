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
2. **`value`** — the raw payload for downstream programmatic use.
   - Scalar SignalK paths (m/s, radians, Pa, K, V, A, fraction) return the
     raw number.
   - `navigation.position` returns the raw `{latitude, longitude}` dict:
     agents calling `read_sensor("navigation.position")` need real
     coordinates for programmatic use, so the dict rides in `value` while
     the spoken form lives in `display`.
   - Tools that return a list (e.g. `get_route`) expose the structured
     payload under a tool-specific key (e.g. `waypoints`), not `value`.
3. **`unit`** — the unit of `value` as a short string (`"knots"`, `"°"`,
   `"V"`, `"A"`, `"hPa"`, `"°C"`, `"m"`, `null`). The unit applies to the
   *converted* display, not the raw SI input.
4. **`timestamp`** — pass-through of SignalK's timestamp as an ISO 8601
   string, or `null`. Not currently humanized.

### TTS-protection rule

Any field that can carry a number the agent might speak must have a
companion `display` string. Specifically:

- Position: raw `{latitude, longitude}` stays in `value` for programmatic
  use, but the agent speaks `display` (cardinal-name lat/lon), never the
  raw pair.
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

## Error handling

A SignalK **404 is not an error** — it means the vessel doesn't publish that
path (no such sensor, or a guessed/misspelled path). The client treats it as
a normal "not available" result: `get_value` returns `{value: None,
timestamp: None}` and `read_sensor` returns `value=None, display=None`. It
does **not** raise.

This is deliberate. Agent runtimes commonly run a per-tool circuit breaker
(e.g. Hermes trips after 3 consecutive `same_tool` failures). A smaller model
that fans out across several guessed paths — `headingTrue`, `headingMagnetic`,
etc. on a vessel with no compass — would otherwise generate a burst of 404s,
each counted as a tool failure, tripping the breaker and blocking the *valid*
reads queued behind them (e.g. `courseOverGroundTrue`). Returning a clean null
keeps a missing path a successful call.

Any other HTTP status (5xx, etc.) and connection/timeout failures are genuine
faults and still raise — those *should* surface to the client.

## Tools

### `read_sensor(path: str)`
- `path` must be a dotted SignalK path under `vessels/self/`.
- Returns `{path, value, display, unit, timestamp}`.
- If the path is absent (SignalK 404), returns `value=None, display=None,
  unit=None, timestamp=None` rather than raising — see **Error handling**. A
  present-but-unpopulated path (e.g. `courseOverGroundTrue` while stationary)
  is reported the same way: `value=None`.
- For `navigation.position`, `value` carries the raw `{latitude, longitude}`
  dict (agents need real coordinates programmatically) and `display` carries
  the full cardinal-name lat/lon for speech.

### `list_paths(prefix: str = None)`
- Returns `{paths: [{path, units, description}, ...], count}`, sorted by `path`.
- Flattens the `vessels/self` tree to one row per value-bearing leaf; `units`
  and `description` come from each leaf's `meta` (`None` when absent).
- `prefix` filters to paths starting with that string (e.g. `"navigation"`,
  `"environment.depth"`). Applied in-process, never interpolated into a URL.
- Carries **no live values** — discovery only. Chain into `read_sensor` for
  values. Paths that don't exist (e.g. an empty heading sentence) never appear,
  so the result is the set of paths actually publishing data.
- A 404 at the tree root returns `{paths: [], count: 0}` (see **Error handling**).

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

### `depth_state()`
- Returns `{below_keel_m, below_surface_m, below_transducer_m, display,
  timestamp}`.
- `display` leads with under-keel clearance (e.g. `"4.2 metres under the
  keel, 5.5 metres of water"`) — `below_keel_m` **is** the clearance under
  the hull, so an agent answers "how's our depth?" / "how close are we to
  running aground?" without guessing paths or doing draft math.
- When `belowKeel` isn't published (e.g. a DBT-only sounder with no keel
  offset), `display` falls back to surface- or transducer-referenced depth,
  explicitly labelled `"under-keel clearance unavailable"` — never passes a
  transducer reading off as keel clearance.
- No depth published → all values `None`, `display` `None` (no fabrication).

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

## v0.2 roadmap

Planned additions, each upholding the same response contract (TTS-safe
`display` per value, raw scalar in `value`, path-injection validation):

- `get_ais_targets(max_distance=None, page=1, page_size=20)` — nearby AIS
  contacts with distance filtering and pagination. Feeds `colregs-mcp`
  collision awareness. Each target carries a spoken `display`
  (e.g. `"cargo vessel, 1.2 nautical miles, bearing North-East"`).
- `get_active_alarms()` — current SignalK notifications/alarms for the
  Engineer agent's anomaly detection. `display` summarizes severity + path.
- `list_paths(prefix=None)` — discover available SignalK paths under
  `vessels/self/`, so agents can explore an unfamiliar tree.

Also planned: WebSocket subscriptions, authenticated write paths, humanized
timestamps (see Out of scope above).

These three were harvested from a review of VesselSense's
`signalk-mcp-server` (see `planning/references/vesselsense-signalk-mcp-comparison.md`).
Their `execute_code` model was deliberately *not* adopted — it discards the
TTS contract and is a reliability risk for the local Hermes 3 8B voice layer.

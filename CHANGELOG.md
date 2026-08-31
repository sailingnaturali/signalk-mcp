# Changelog

## Unreleased

## v0.8.0 — 2026-08-31

### Changed

- **MCP SDK v2** — migrated to `mcp>=2.1`, the SDK line that speaks the
  stateless 2026-07-28 MCP spec revision (`server/discover`, per-request
  version/capabilities, `resultType`). Handlers moved from the removed
  decorator API to constructor `on_list_tools`/`on_call_tool` params. Tool
  failures (unknown tool, no active route, SignalK unreachable) are caught in
  the handler and returned as `is_error` tool results so they stay visible to
  the calling LLM — the v2 SDK would otherwise surface them as protocol
  errors the model never sees.
- Tool results now also carry `structuredContent` alongside the JSON text.
- Server reports its own package version (previously the SDK filled this in;
  under v2 it would have been blank). Dropped the stale, unused
  `__init__.__version__`.

### Fixed

- Clean shutdown no longer prints a `CancelledError` traceback when the
  TimezoneFinder warmup task is cancelled mid-flight.

## v0.7.0 — 2026-08-10

### Added

- **`sk` CLI** — the same `tools.py` functions the MCP server exposes, as a
  shell command, for the contexts MCP cannot reach: ssh sessions on the boat
  Pi, cron/launchd jobs, headless `claude -p`, non-MCP agents. Compact JSON on
  stdout, identical in shape to the MCP tool results. Deliberately a dispatch
  table over `tools.py` rather than its own formatting, so the two front ends
  cannot drift.

  ```bash
  sk depth | sk battery | sk alarms | sk read environment.wind.speedTrue
  ```

  It is not a token optimization — benchmarking (see the MCP-vs-CLI measurement
  in the planning repo) found the MCP surface cheaper than a Bash+CLI one,
  because enabling the Bash tool costs more prompt than all seven MCP schemas
  combined. It earns its place on reach, not cost.

### Fixed

- **`battery_state` returned all-nulls on a vessel with named banks.** The
  default was `bank="0"` (the SignalK convention), but a vessel publishing
  `electrical.batteries.house` made the bare tool answer "no battery data" on a
  boat that was publishing battery data the whole time — an agent only got a
  reading if the asker happened to say "house". With no bank named, `"0"` is
  still tried first, then the vessel's own banks are discovered from the
  `electrical.batteries` subtree (read off that same fetch, no second round
  trip). An explicitly named bank is never second-guessed: answering about a
  different battery than the one asked for is worse than answering "no data".
  Several banks with no `house` among them stay ambiguous on purpose and come
  back as `available_banks` — `start` and `house` are not interchangeable.

## v0.5.0 — 2026-06-04

### Added

- `get_active_alarms`: returns active SignalK notifications (non-`normal`
  states), most severe first, with the `notifications.` prefix stripped so each
  path feeds vessel-knowledge `explain_notification`. Backs the Engineer agent's
  "anything wrong?" triage.

## v0.3.0 — 2026-06-03

### Added

- `list_paths` tool — discover the SignalK paths a vessel actually publishes, each with `units` and `description` from `meta`, optional `prefix` filter. Lets an agent find the real path (`environment.depth.belowTransducer`) instead of guessing wrong namespaces (`sensors.depth`, `sailboatLogic.speedThroughWater`). No live values in the output — chain `list_paths` → `read_sensor`. A 404 at the tree root returns an empty list, consistent with the v0.2.0 404 rule.

## v0.2.0 — 2026-06-03

### Added

- `get_local_time` tool — GPS-aware timezone localization
- Human-readable display strings for sensor readings (knots, °C, hPa, compass labels)
- TTS-protection contract: every numeric response now has a spoken `display` string (battery voltage/current/SOC, position, sensor readings)
- `SPEC.md` documenting response contract and conversion table
- Port/starboard semantics for relative wind angles (`angleApparent`, `angleTrueWater`, `angleTrueGround`)
- East/West indicator for `navigation.magneticVariation`
- Compass labels for `directionTrue` / `directionMagnetic`

### Fixed

- `environment.wind.angleApparent` now uses the canonical SignalK path name (was incorrectly `angleApparentWater`)
- `get_route` no longer crashes on GeoJSON coordinates with elevation (`[lon, lat, elev]`)
- `get_route` now accepts both Feature and FeatureCollection-shaped route resources
- `call_tool` accepts `arguments=None` (some MCP clients omit it)
- Path/bank arguments are validated against `[A-Za-z0-9._-]+` before URL interpolation
- `get_local_time` logs network/auth failures instead of swallowing them silently

### Changed

- A SignalK 404 (path not published) now returns `value=None` instead of raising. Missing/guessed paths are a normal "not available" result, not a tool failure — prevents a burst of 404s (e.g. heading paths on a vessel with no compass) from tripping an agent runtime's consecutive-failure circuit breaker and blocking valid reads. Non-404 errors (5xx, connection) still raise.
- `SignalKClient` is now shared across tool calls (one httpx connection pool per process)
- `TimezoneFinder` initialization deferred until first `get_local_time` call (was loading ~50MB at import)
- `build_server(client)` now takes the client as a required argument; caller owns its lifetime
- Dropped unused `websockets` dependency (deferred to v0.2)

## v0.1.0 — 2026-05-17

### Added

- MCP server entry point (stdio transport)
- `SignalKClient` — async REST wrapper, dotted-path → URL conversion
- Tools: `read_sensor`, `get_route`, `battery_state`
- Integration test skeleton (activated via `SIGNALK_TEST_URL`)
- GitHub Actions: pytest + mcp-scanner security scan
- MIT license

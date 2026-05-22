# Changelog

## Unreleased

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

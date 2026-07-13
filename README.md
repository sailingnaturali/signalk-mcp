# signalk-mcp

An MCP server exposing a SignalK instance as a tool surface for AI agents.

Part of the [Naturali](https://sailingnaturali.com) open-source boat agent stack.

## What it does

Wraps a SignalK server (REST + WebSocket) and exposes the most useful marine data points as MCP tools that any compatible agent runtime (Poseidon, Claude Code, etc.) can call.

### Tools provided

- `read_sensor(path)` — Read a SignalK path (e.g., `navigation.position`, `environment.wind.speedTrue`)
- `get_route()` — Read the current planned route (waypoints, ETAs)
- `battery_state(bank)` — Read battery state of charge, voltage, current
- `depth_state()` — Water depth with under-keel clearance first (answers "how's our depth?" / "how close are we to running aground?")
- `get_local_time()` — Current time localized to the vessel's GPS position
- `list_paths(prefix)` — Discover which SignalK paths the vessel publishes

See [SPEC.md](SPEC.md) for the response contract.

## Why a separate server?

[VesselSense/signalk-mcp-server](https://github.com/VesselSense/signalk-mcp-server)
already does SignalK-on-MCP well: one `execute_code` tool, the agent writes its
own queries — a great fit for frontier models. `signalk-mcp` makes the opposite
bet: discrete named tools with TTS-safe `display` strings, tuned for voice-first
and small local models, where reliability and a speech contract matter more than
query flexibility. Neither is universally better — pick the surface for the agent
you actually run.

Full comparison, including the failure modes:
[Discrete tools vs execute_code](https://engineering.sailingnaturali.com/discrete-tools-vs-execute-code-mcp-for-voice-agents/).

## Installation

```bash
uv tool install signalk-mcp
```

## Configuration

Set the SignalK base URL via environment variable:

```bash
export SIGNALK_URL=http://naturalaspi:3000
signalk-mcp
```

## License

MIT. See LICENSE.

## Security

If you find a security issue, see SECURITY.md.

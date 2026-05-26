# signalk-mcp

An MCP server exposing a SignalK instance as a tool surface for AI agents.

Part of the [Naturali](https://sailingnaturali.com) open-source boat agent stack.

## What it does

Wraps a SignalK server (REST + WebSocket) and exposes the most useful marine data points as MCP tools that any compatible agent runtime (Hermes Agent, Claude Code, etc.) can call.

### Tools provided

- `read_sensor(path)` — Read a SignalK path (e.g., `navigation.position`, `environment.wind.speedTrue`)
- `get_route()` — Read the current planned route (waypoints, ETAs)
- `battery_state(bank)` — Read battery state of charge, voltage, current
- `get_local_time()` — Current time localized to the vessel's GPS position
- *(more in v0.2+)*

See [SPEC.md](SPEC.md) for the response contract.

## Installation

```bash
uv tool install signalk-mcp
```

## Configuration

Set the SignalK base URL via environment variable:

```bash
export SIGNALK_URL=http://naturalaspi.local:3000
signalk-mcp
```

## License

MIT. See LICENSE.

## Security

If you find a security issue, see SECURITY.md.

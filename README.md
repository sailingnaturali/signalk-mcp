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

## Why a separate server?

There is already a capable SignalK MCP server —
[VesselSense/signalk-mcp-server](https://github.com/VesselSense/signalk-mcp-server)
(TypeScript, MIT). It's well-built and worth a look. We built a separate
server rather than contributing to it because the two have genuinely
different design goals:

- **VesselSense exposes a single `execute_code` tool** — the agent writes
  JavaScript that runs in a sandboxed V8 isolate and queries SignalK. That's
  an excellent fit for a large frontier model doing complex, multi-step
  queries where token efficiency matters.
- **`signalk-mcp` exposes discrete, named tools** (`read_sensor`,
  `battery_state`, …) and is optimized for a **voice-first, local model**.
  Our target runtime is a small model (Hermes 3 8B) driving a text-to-speech
  front-end on a boat. For that, two things matter more than token
  efficiency:
  1. **Reliability.** A named tool with one argument is far more robust than
     asking a small local model to write correct JavaScript for "what's my
     battery?"
  2. **A speech contract.** Every value carries a `display` string the agent
     can speak verbatim — spelled-out units (`"knots"`, not `"kn"`), cardinal
     lat/lon, no symbols a TTS engine mispronounces. See
     [SPEC.md](SPEC.md#tts-protection-rule).

Neither approach is universally better — they're tuned for different agents.
If you're driving SignalK with a frontier model and want maximum query
flexibility, VesselSense is likely the better choice. If you want simple,
reliable, speakable tools for a local or voice-first agent, that's what this
server is for.

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

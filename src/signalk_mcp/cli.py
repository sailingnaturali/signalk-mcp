"""``sk`` — the signalk-mcp tools as a shell command, for agents with Bash.

Same functions as the MCP server (``tools.py``), different front end: MCP pays
its tool schemas into every context up front, a CLI costs nothing until it is
called. Which is cheaper is an empirical question — see poseidon.bench's
``--arm`` experiment in naturali-agents.

Output is compact JSON on stdout, identical to what the MCP tools return, so
the two front ends are comparable byte-for-byte. Reads are anonymous under
SignalK's ``allow_readonly``; no token needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from signalk_mcp import tools
from signalk_mcp.client import SignalKClient

# name -> (function, arg name or None). Mirrors server.py's dispatch; keeping
# both fed from tools.py is what stops the two front ends from drifting.
COMMANDS = {
    "alarms": (tools.get_active_alarms, None),
    "battery": (tools.battery_state, "bank"),
    "depth": (tools.depth_state, None),
    "time": (tools.get_local_time, None),
    "route": (tools.get_route, None),
    "paths": (tools.list_paths, "prefix"),
    "read": (tools.read_sensor, "path"),
}


async def _run(name: str, arg: str | None) -> dict:
    func, arg_name = COMMANDS[name]
    client = SignalKClient(os.environ.get("SIGNALK_URL", "http://localhost:3000"))
    try:
        if arg_name and arg is not None:
            return await func(client, **{arg_name: arg})
        return await func(client)
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sk",
        description="SignalK vessel data as JSON. Reads the live boat server.",
        epilog="examples: sk depth | sk battery | sk alarms | "
               "sk read tanks.freshWater.0.currentLevel | sk paths tanks",
    )
    parser.add_argument("command", choices=sorted(COMMANDS),
                        help="alarms: active notifications, worst first. "
                             "battery [bank]: state of charge/voltage/current. "
                             "depth: below keel/transducer/surface. "
                             "time: vessel local time. route: active route. "
                             "paths [prefix]: list available paths. "
                             "read <path>: any path's current value.")
    parser.add_argument("arg", nargs="?",
                        help="path for read, prefix for paths, bank for battery")
    args = parser.parse_args()

    if args.command == "read" and not args.arg:
        parser.error("read needs a path, e.g. sk read environment.wind.speedTrue")

    try:
        result = asyncio.run(_run(args.command, args.arg))
    except Exception as exc:  # noqa: BLE001 — a CLI reports, it does not traceback
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc

    # ponytail: no --pretty. Agents read this, and whitespace is billed.
    json.dump(result, sys.stdout, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

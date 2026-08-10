"""Checks for the `sk` CLI front end.

The CLI's whole job is to stay a thin dispatch over tools.py — the same
functions the MCP server exposes. What can actually break: a command mapping to
a function that no longer exists, an arg name that no longer matches, or the
`read` path guard going missing.
"""
from __future__ import annotations

import inspect

import pytest

from signalk_mcp import tools
from signalk_mcp.cli import COMMANDS, main


def test_every_command_maps_to_a_real_tool_function():
    for name, (func, arg_name) in COMMANDS.items():
        assert getattr(tools, func.__name__, None) is func, f"{name} is not a tools.py function"
        params = inspect.signature(func).parameters
        assert "client" in params, f"{name} does not take a client"
        if arg_name:
            assert arg_name in params, f"{name} passes {arg_name!r}, which {func.__name__} lacks"


def test_read_without_a_path_is_rejected(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["sk", "read"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0
    assert "needs a path" in capsys.readouterr().err


def test_unknown_command_is_rejected(monkeypatch):
    monkeypatch.setattr("sys.argv", ["sk", "nonsense"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0

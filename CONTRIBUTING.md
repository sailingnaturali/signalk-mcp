# Contributing

## Development

```sh
uv sync
uv run pytest
```

`server.py` is the MCP wiring; the tool logic lives in `tools.py` and is
shared with the `sk` CLI. Tool behavior changes need a test.

## Releasing

Version bumps ride the PR that motivates them: bump `version` in
`pyproject.toml` and add a `CHANGELOG.md` entry in the same PR.

That's the whole release. On merge, the `version tagged` workflow sees the
new version has no tag and pushes `v<version>` at the merge commit
automatically. Merges that don't bump the version are a green no-op.

# Contributing

## Development

```sh
uv sync
uv run pytest
```

`server.py` is the MCP wiring; the tool logic lives in `tools.py` and is
shared with the `sk` CLI. Tool behavior changes need a test.

## Releasing

Version bumps ride the PR that motivates them:

1. In the PR: bump `version` in `pyproject.toml` and add a `CHANGELOG.md`
   entry.
2. After merge, tag the release from `main`:

   ```sh
   git switch main && git pull
   git tag v<version> && git push --tags
   ```

The `version tagged` workflow enforces this: it fails on any `main` push
whose `pyproject.toml` version has no matching tag. Expect a red run on
the merge commit — that's the reminder, not a breakage. Pushing the tag
starts its own green run, but the red run on the merge commit stays red
in history until you re-run it:

```sh
gh run rerun <run-id>   # now finds the tag and passes
```

Or ignore it — once the tag exists, the failure is purely cosmetic.

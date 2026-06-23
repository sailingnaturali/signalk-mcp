"""Thin async wrapper around SignalK's REST API."""

from __future__ import annotations

import re

import httpx
from naturali_mcp_netutil import resolve_local_host

_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Resource hrefs from the server's own payloads still reach a URL sink (R5).
_HREF_RE = re.compile(r"^/resources/[A-Za-z0-9._/-]+$")


def validate_path_segment(segment: str, label: str = "path") -> None:
    """Reject anything outside [A-Za-z0-9._-]+ before interpolating into a URL.

    Prevents path traversal and crashes from agent-supplied junk. See SPEC.md.
    """
    if not segment or not _PATH_RE.match(segment):
        raise ValueError(f"invalid {label}: {segment!r}")


class SignalKClient:
    """Async client for SignalK REST API.

    Converts dotted SignalK paths (e.g. ``environment.wind.speedTrue``) to URL paths.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = resolve_local_host(base_url.rstrip("/"))
        self._http = httpx.AsyncClient(timeout=5.0)

    async def get_value(self, path: str) -> dict:
        """Fetch a SignalK path's value object. Returns the raw API response dict.

        A 404 means the vessel simply doesn't publish that path — a normal
        "not available" result, not a failure. We return a null-valued dict
        rather than raising so that missing/guessed paths don't register as
        tool failures (which can trip a client's consecutive-failure circuit
        breaker). Any other HTTP error (5xx, etc.) is a real fault and still
        raises.
        """
        validate_path_segment(path, "path")
        url_path = path.replace(".", "/")
        url = f"{self.base_url}/signalk/v1/api/vessels/self/{url_path}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return {"value": None, "timestamp": None}
        resp.raise_for_status()
        return resp.json()

    async def get_self_tree(self) -> dict:
        """Fetch the entire ``vessels/self`` tree (for path discovery).

        A 404 (no self vessel published yet) returns an empty dict rather than
        raising — same "absent is not a failure" rule as ``get_value``. Other
        HTTP errors still raise.
        """
        url = f"{self.base_url}/signalk/v1/api/vessels/self/"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def get_notifications(self) -> dict:
        """Fetch the ``notifications`` subtree under ``vessels/self``.

        Returns the subtree rooted at ``notifications`` (its keys are the
        monitored path segments, e.g. ``propulsion``), so leaf paths come out
        already stripped of the ``notifications.`` prefix. A 404 (nothing
        published) returns an empty dict — same "absent is not a failure" rule
        as ``get_self_tree``.
        """
        url = f"{self.base_url}/signalk/v1/api/vessels/self/notifications"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def get_resource(self, href: str) -> dict:
        """Fetch a resource by its SignalK API href (e.g. ``/resources/routes/r-1``).

        The href comes from the vessel's own server, but it still reaches a URL
        sink — validate like every other segment (no ``..``, no ``//host``).
        A 404 (stale/deleted href) returns ``{}`` — the same "absent is not a
        failure" rule as the rest of the client.
        """
        if not _HREF_RE.match(href) or ".." in href:
            raise ValueError(f"invalid resource href: {href!r}")
        url = f"{self.base_url}/signalk/v1/api{href}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()

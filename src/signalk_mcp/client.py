"""Thin async wrapper around SignalK's REST API."""

from __future__ import annotations

import re

import httpx

_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=5.0)

    async def get_value(self, path: str) -> dict:
        """Fetch a SignalK path's value object. Returns the raw API response dict."""
        validate_path_segment(path, "path")
        url_path = path.replace(".", "/")
        url = f"{self.base_url}/signalk/v1/api/vessels/self/{url_path}"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_resource(self, href: str) -> dict:
        """Fetch a resource by its SignalK API href (e.g. ``/resources/routes/r-1``)."""
        url = f"{self.base_url}/signalk/v1/api{href}"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()

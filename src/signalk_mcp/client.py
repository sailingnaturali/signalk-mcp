"""Thin async wrapper around SignalK's REST API."""

from __future__ import annotations

import httpx


class SignalKClient:
    """Async client for SignalK REST API.

    Converts dotted SignalK paths (e.g. ``environment.wind.speedTrue``) to URL paths.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=5.0)

    async def get_value(self, path: str) -> dict:
        """Fetch a SignalK path's value object. Returns the raw API response dict."""
        url_path = path.replace(".", "/")
        url = f"{self.base_url}/signalk/v1/api/vessels/self/{url_path}"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()

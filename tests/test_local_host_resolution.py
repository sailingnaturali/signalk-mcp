"""mDNS .local hosts hang httpx's async connect on macOS (IPv6 Happy-Eyeballs
waits out the full timeout before IPv4 fallback). SignalKClient resolves a
.local host to its IPv4 at construction time and connects to the IP instead."""
import socket
from unittest.mock import patch

from signalk_mcp.client import SignalKClient


def _fake_getaddrinfo(ip):
    def _f(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]
    return _f


def test_local_host_resolved_to_ipv4():
    with patch("signalk_mcp.client.socket.getaddrinfo",
               _fake_getaddrinfo("192.168.68.60")):
        c = SignalKClient("http://naturalaspi.local:3000")
    assert c.base_url == "http://192.168.68.60:3000"


def test_non_local_host_unchanged():
    assert SignalKClient("http://192.168.68.60:3000").base_url == \
        "http://192.168.68.60:3000"
    assert SignalKClient("http://localhost:3000").base_url == \
        "http://localhost:3000"


def test_local_resolution_failure_falls_back_to_hostname():
    def _boom(*a, **k):
        raise socket.gaierror("name resolution failed")

    with patch("signalk_mcp.client.socket.getaddrinfo", _boom):
        c = SignalKClient("http://naturalaspi.local:3000")
    assert c.base_url == "http://naturalaspi.local:3000"


def test_local_host_forces_ipv4_family():
    captured = {}

    def _spy(host, port, family=0, *a, **k):
        captured["family"] = family
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.68.60", port or 0))]

    with patch("signalk_mcp.client.socket.getaddrinfo", _spy):
        SignalKClient("http://naturalaspi.local:3000")
    assert captured["family"] == socket.AF_INET

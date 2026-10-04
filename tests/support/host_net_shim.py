"""Host-only pytest plugin: tolerate a flaky route to Cloudflare-fronted RPC hosts. Test process only.

Observed on a Windows host: studio.genlayer.com resolves to AAAA records first (the host's IPv6 route is
black-holed) and one of its two A records intermittently stalls ~8-20 s on connect. Python then fails with
`ConnectTimeoutError` before any request is sent. curl on the same host is fine because it races addresses.

This plugin, only when CREDO_HOST_NET_FIX=1:
  1. filters `socket.getaddrinfo` results to IPv4,
  2. gives `requests` a 6 s connect timeout where the caller set none,
  3. retries `requests.exceptions.ConnectTimeout` (the connection was never established, so the request was
     never sent: this cannot double-submit a transaction) up to 6 times.

It changes no system setting, no contract code and no assertion. Read timeouts and every other error propagate
unchanged.

Use:  CREDO_HOST_NET_FIX=1 PYTHONPATH=. gltest tests/integration/ -p tests.support.host_net_shim --network studionet
"""
import os
import socket

_orig_getaddrinfo = socket.getaddrinfo
RETRIES = 6
CONNECT_TIMEOUT_S = 6


def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
    res = _orig_getaddrinfo(host, port, family, type, proto, flags)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res


def pytest_configure(config) -> None:
    if os.environ.get("CREDO_HOST_NET_FIX") != "1":
        return
    socket.getaddrinfo = _ipv4_first
    import requests
    from requests.adapters import HTTPAdapter

    orig_send = HTTPAdapter.send

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (CONNECT_TIMEOUT_S, 300)
        last = None
        for _ in range(RETRIES):
            try:
                return orig_send(self, request, **kwargs)
            except requests.exceptions.ConnectTimeout as e:
                last = e
        raise last

    HTTPAdapter.send = send

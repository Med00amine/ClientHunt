"""SSRF-safe, robots-respecting page fetcher for company research. Retrieved content is untrusted data."""
from __future__ import annotations

import ipaddress
import socket
import urllib.robotparser
from urllib.parse import urljoin, urlsplit

import httpx

from ..config import get_settings

MAX_BYTES = 500_000


class FetchBlocked(Exception):
    pass


def resolve_public(host: str) -> list[str]:
    """Return resolved IPs; raise if any is non-public. Replaceable in tests."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchBlocked(f"cannot resolve {host}") from e
    ips = sorted({i[4][0] for i in infos})
    for ip in ips:
        if not ipaddress.ip_address(ip).is_global:
            raise FetchBlocked(f"{host} resolves to non-public address")
    return ips


class SafeFetcher:
    def __init__(self, client: httpx.Client | None = None, resolver=resolve_public):
        self.client = client or httpx.Client(timeout=15, follow_redirects=False,
                                             headers={"User-Agent": get_settings().http_user_agent})
        self.resolver = resolver
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _check_url(self, url: str) -> None:
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise FetchBlocked("only http(s) URLs are allowed")
        if p.username or p.password:
            raise FetchBlocked("credentials in URL not allowed")
        self.resolver(p.hostname)

    def _allowed_by_robots(self, url: str) -> bool:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._check_url(origin + "/robots.txt")
                r = self.client.get(origin + "/robots.txt")
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[origin] = rp
                else:
                    self._robots[origin] = None  # no robots file: allowed
            except (FetchBlocked, httpx.HTTPError):
                self._robots[origin] = None
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(get_settings().http_user_agent, url)

    def get_html(self, url: str, max_redirects: int = 3) -> tuple[str, str]:
        """Returns (final_url, html). Raises FetchBlocked / httpx errors."""
        for _ in range(max_redirects + 1):
            self._check_url(url)
            if not self._allowed_by_robots(url):
                raise FetchBlocked("disallowed by robots.txt")
            with self.client.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise FetchBlocked(f"HTTP {r.status_code}")
                if "html" not in r.headers.get("content-type", "text/html").lower():
                    raise FetchBlocked("not an HTML page")
                buf = b""
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        break
                return url, buf[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
        raise FetchBlocked("too many redirects")

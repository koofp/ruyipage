"""Kookeey dynamic proxy API client.

The client signs every request with Base64(HMAC-SHA1 binary digest), disables
TLS certificate verification as required by the Kookeey integration, and
returns proxy endpoints in URL or tuple form.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias
from urllib.parse import quote, urlencode

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE_URL = "https://www.kookeey.com/clientapi"
GEO_MAP: dict[str, int] = {
    "US": 43,
    "JP": 193,
    "GB": 93,
    "HK": 113,
    "SG": 195,
    "KR": 110,
    "TW": 181,
    "DE": 82,
    "NL": 150,
    "AU": 14,
    "IN": 100,
    "CA": 39,
    "FR": 75,
    "BR": 32,
    "global": 0,
}

ProxyTuple: TypeAlias = tuple[str, int, str, str]
ProxyResult: TypeAlias = str | ProxyTuple
OutputFormat: TypeAlias = Literal["url", "tuple"]
RotationStrategy: TypeAlias = Literal["random", "sticky"]


class KookeeyError(RuntimeError):
    """Base class for Kookeey API client errors."""


class KookeeyNetworkError(KookeeyError):
    """Raised when a request cannot reach the Kookeey API."""


class KookeeyAPIError(KookeeyError):
    """Raised when Kookeey returns an invalid or unsuccessful API response."""


@dataclass(frozen=True)
class ProxyEndpoint:
    """Normalized endpoint fields returned from one Kookeey line."""

    host: str
    port: int
    username: str
    password: str

    def as_tuple(self) -> ProxyTuple:
        """Return ``(host, port, username, password)``."""
        return (self.host, self.port, self.username, self.password)

    def as_url(self, protocol: str) -> str:
        """Return a safely escaped proxy URL using ``protocol``."""
        host = self.host
        if ":" in host and not host.startswith("["):
            host = "[{}]".format(host)
        user = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return "{}://{}:{}@{}:{}".format(protocol, user, password, host, self.port)


class KookeeyAPI:
    """Client for Kookeey's signed proxy-line API.

    Args:
        access_id: Kookeey API access ID (sent as ``accessid``).
        token: Kookeey signing token. It is never printed by this module.
        base_url: API root. Defaults to Kookeey's official ``/clientapi`` URL.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        access_id: str | int,
        token: str,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 20.0,
    ) -> None:
        if not str(access_id).strip():
            raise ValueError("access_id must not be empty")
        if not token:
            raise ValueError("token must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.access_id = str(access_id)
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.session = requests.Session()
        self.session.verify = False

    def get_proxy_list(
        self,
        proxy_type: int = 2,
        geo_id: int = 0,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Return a page of Kookeey proxy lines.

        Args:
            proxy_type: Product type: ``1`` dynamic DC, ``2`` dynamic
                residential, or ``4`` static ISP.
            geo_id: Kookeey geographic ID; use :data:`GEO_MAP` for built-ins.
            page: One-based result page.
            page_size: Requested page size. It is sent as ``psize``.

        Returns:
            The complete Kookeey JSON response dictionary.

        Raises:
            KookeeyNetworkError: The API cannot be reached.
            KookeeyAPIError: The API rejects the request or returns bad JSON.
        """
        if proxy_type not in (1, 2, 4):
            raise ValueError("proxy_type must be one of 1, 2, or 4")
        if geo_id < 0:
            raise ValueError("geo_id must be non-negative")
        if page < 1:
            raise ValueError("page must be at least 1")
        if page_size < 1:
            raise ValueError("page_size must be at least 1")

        print(
            "[kookeey] listing lines: type={}, geo_id={}, page={}, page_size={}".format(
                proxy_type, geo_id, page, page_size
            )
        )
        return self._get(
            "/pl",
            [("t", proxy_type), ("g", geo_id), ("page", page), ("page_size", page_size)],
        )

    def switch_ip(self, port_id: int | str) -> dict[str, Any]:
        """Request an IP/session change for one dynamic proxy line.

        Args:
            port_id: Kookeey ``portid`` of the line to rotate.

        Returns:
            The complete Kookeey JSON response dictionary.

        Raises:
            KookeeyNetworkError: The API cannot be reached.
            KookeeyAPIError: The API rejects the request.
        """
        port_id = self._validate_port_id(port_id)
        print("[kookeey] switching session for port {}".format(port_id))
        return self._get("/chgsessionip", [("p", port_id)])

    def get_current_ip(self, port_id: int | str) -> str:
        """Return the API-reported current egress IP for a proxy line.

        Kookeey documents this endpoint as cached; third-party IP-check
        services are more appropriate for verifying a dynamic rotation.

        Args:
            port_id: Kookeey ``portid`` of the line.

        Returns:
            The current egress IP string returned by the API.

        Raises:
            KookeeyNetworkError: The API cannot be reached.
            KookeeyAPIError: The API response does not contain an IP value.
        """
        port_id = self._validate_port_id(port_id)
        print("[kookeey] reading current IP for port {}".format(port_id))
        response = self._get("/ip", [("p", port_id)])
        data = response.get("data")
        if isinstance(data, str) and data:
            return data
        if isinstance(data, dict):
            for key in ("ip", "proxyip", "current_ip"):
                value = data.get(key)
                if value:
                    return str(value)
        raise KookeeyAPIError("Kookeey /ip response did not contain an IP value")

    def fetch_proxies(
        self,
        count: int = 1,
        geo_id: int = 0,
        protocol: str = "socks5",
        output_format: OutputFormat = "url",
        switch_ip: bool = True,
        rotation_strategy: RotationStrategy = "random",
        proxy_type: int = 2,
    ) -> list[ProxyResult]:
        """Fetch up to ``count`` proxy endpoints from the account's lines.

        The method requests Kookeey lines, takes the first usable ``count``
        lines, optionally requests a session/IP switch for each line, and
        converts each endpoint to the requested output representation.

        Args:
            count: Maximum number of proxy lines to return.
            geo_id: Kookeey geographic ID; use :data:`GEO_MAP` if desired.
            protocol: Output URL protocol: ``http``, ``https``, or ``socks5``.
            output_format: ``"url"`` for proxy URLs or ``"tuple"`` for
                ``(host, port, username, password)`` tuples.
            switch_ip: If true, call :meth:`switch_ip` before returning each
                selected proxy line.
            rotation_strategy: ``"random"`` or ``"sticky"``. This controls
                caller intent/documentation; manual rotation is still governed
                by ``switch_ip`` and the line's Kookeey rotation settings.
            proxy_type: Kookeey product type passed to :meth:`get_proxy_list`.

        Returns:
            A list containing at most ``count`` URL strings or endpoint tuples.

        Raises:
            ValueError: An argument is unsupported.
            KookeeyNetworkError: An API/proxy request cannot be reached.
            KookeeyAPIError: Kookeey returns no usable proxy line.
        """
        if count < 1:
            raise ValueError("count must be at least 1")
        protocol = protocol.lower()
        if protocol not in {"http", "https", "socks5"}:
            raise ValueError("protocol must be 'http', 'https', or 'socks5'")
        if output_format not in {"url", "tuple"}:
            raise ValueError("output_format must be 'url' or 'tuple'")
        if rotation_strategy not in {"random", "sticky"}:
            raise ValueError("rotation_strategy must be 'random' or 'sticky'")

        listing = self.get_proxy_list(
            proxy_type=proxy_type,
            geo_id=geo_id,
            page=1,
            page_size=max(50, count),
        )
        data = listing.get("data") or {}
        lines = data.get("list") if isinstance(data, dict) else None
        if not isinstance(lines, list) or not lines:
            raise KookeeyAPIError("Kookeey returned no proxy lines for the requested filters")

        results: list[ProxyResult] = []
        for line in lines:
            if len(results) >= count:
                break
            if not isinstance(line, dict):
                continue
            endpoint = self._endpoint_from_line(line)
            port_id = line.get("portid") or line.get("port_id")
            if switch_ip:
                if port_id is None:
                    raise KookeeyAPIError("proxy line is missing portid; cannot switch its session")
                self.switch_ip(port_id)
            if output_format == "url":
                results.append(endpoint.as_url(protocol))
            else:
                results.append(endpoint.as_tuple())

        if not results:
            raise KookeeyAPIError("Kookeey returned lines without usable host/port/auth data")
        if len(results) < count:
            print("[kookeey] requested {} proxies; only {} usable line(s) returned".format(count, len(results)))
        print("[kookeey] prepared {} {} proxy endpoint(s), rotation={}".format(
            len(results), protocol, rotation_strategy
        ))
        return results

    def test_proxy(
        self,
        proxy_url: str,
        test_url: str = "https://api.ipify.org?format=json",
    ) -> str:
        """Test one proxy and return its egress IP or a readable error string.

        Args:
            proxy_url: Complete HTTP(S) or SOCKS5 proxy URL.
            test_url: IP-check endpoint returning JSON or plain text.

        Returns:
            An IP string on success, otherwise ``"ERROR (network): ..."`` or
            ``"ERROR (response): ..."``.
        """
        print("[kookeey] testing proxy against {}".format(test_url))
        try:
            response = self.session.get(
                test_url,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=self.timeout,
                verify=False,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            message = "ERROR (network): {}: {}".format(type(exc).__name__, exc)
            print("[kookeey] {}".format(message))
            return message

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in ("ip", "origin", "query"):
                value = payload.get(key)
                if value:
                    return str(value)
        text = response.text.strip()
        if text:
            return text
        message = "ERROR (response): IP test returned an empty body"
        print("[kookeey] {}".format(message))
        return message

    def _get(self, path: str, params: list[tuple[str, Any]]) -> dict[str, Any]:
        """Sign and execute one Kookeey GET request."""
        timestamp = str(int(time.time()))
        normalized = [(key, str(value)) for key, value in params]
        param_str = urlencode(normalized)
        sign_str = "{}&ts={}".format(param_str, timestamp) if param_str else "ts={}".format(timestamp)
        signature = base64.b64encode(
            hmac.new(self._token.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha1).hexdigest().encode("utf-8")
        ).decode("ascii")
        # Base64 can contain +/= — URL-encode for query-string safety.
        signature = quote(signature, safe="")
        url = "{}{}?accessid={}&signature={}".format(
            self.base_url, path, self.access_id, signature)
        if param_str:
            url += "&" + param_str
        url += "&ts=" + timestamp

        try:
            response = self.session.get(url, timeout=self.timeout, verify=False)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise KookeeyNetworkError("GET {} failed: {}".format(path, exc)) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise KookeeyAPIError("GET {} returned invalid JSON".format(path)) from exc
        if not isinstance(payload, dict):
            raise KookeeyAPIError("GET {} returned a non-object response".format(path))

        code = payload.get("code")
        if payload.get("success") is False or code not in (None, 0, "0"):
            message = payload.get("msg") or payload.get("message") or "unknown Kookeey API error"
            raise KookeeyAPIError("GET {} failed (code={}): {}".format(path, code, message))
        return payload

    @staticmethod
    def _validate_port_id(port_id: int | str) -> int:
        """Validate and normalize one Kookeey line ID."""
        try:
            value = int(port_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("port_id must be an integer") from exc
        if value <= 0:
            raise ValueError("port_id must be positive")
        return value

    @staticmethod
    def _endpoint_from_line(line: dict[str, Any]) -> ProxyEndpoint:
        """Extract a host, port, and auth pair from one API line record."""
        host = str(line.get("proxydomain") or line.get("proxyip") or "").strip()
        try:
            port = int(line.get("proxyport"))
        except (TypeError, ValueError) as exc:
            raise KookeeyAPIError("proxy line has no valid proxyport") from exc
        authstr = str(line.get("authstr") or "")
        if not host or not authstr or ":" not in authstr:
            raise KookeeyAPIError("proxy line has no usable host or authstr")
        username, password = authstr.split(":", 1)
        if not username or not password:
            raise KookeeyAPIError("proxy line contains an empty username or password")
        return ProxyEndpoint(host=host, port=port, username=username, password=password)

    # ── 提取模式（无需端口线路）──

    def get_extraction_auth(self) -> dict[str, str]:
        """Get extraction-mode auth credentials via /resauth.
        Returns ``{authname, authpwd}``."""
        return self._get("/resauth", []).get("data", {})

    def generate_extraction_proxies(
        self,
        count: int = 5,
        country_code: str = "US",
        sticky: bool = False,
        protocol: str = "http",
    ) -> list[str]:
        """Generate extraction-mode proxy URLs (no port line purchase needed).

        Format:
          ``{protocol}://{userId}-{authname}:{authpwd}-{country}-{session}@gate.kookeey.info:1000``

        Args:
            count:         number of proxy URLs
            country_code:  ISO-3166-1 alpha-2 (e.g. ``"JP"``, ``"US"``) or ``"global"``
            sticky:        reuse the same session id (sticky IP)
            protocol:      ``"http"`` or ``"socks5"``
        """
        import random

        auth = self.get_extraction_auth()
        username = auth.get("authname", "")
        password = auth.get("authpwd", "")
        if not username or not password:
            raise KookeeyAPIError("extraction auth missing — check Kookeey security settings")

        proxies: list[str] = []
        for _ in range(count):
            session = str(random.randint(10000000, 99999999))
            if sticky and proxies:
                session = proxies[0].split("-")[-1].split("@")[0]
            proxies.append(
                "{}://{}-{}:{}-{}-{}@gate.kookeey.info:1000".format(
                    protocol, self.access_id, username, password, country_code, session))
        print("[kookeey] generated {} extraction proxies for {}".format(len(proxies), country_code))
        return proxies

    # ── 提取模式（无需端口线路，API 自动生成代理 URL）──

    def get_extraction_auth(self) -> dict[str, str]:
        """Get extraction-mode authname / authpwd via ``/resauth``."""
        return self._get("/resauth", []).get("data", {})

    def generate_extraction_proxies(
        self,
        count: int = 5,
        country_code: str = "US",
        sticky: bool = False,
        protocol: str = "http",
    ) -> list[str]:
        """Generate extraction-mode proxy URLs.

        Format:
          ``{protocol}://{uid}-{uname}:{pwd}-{ctry}-{sid}@gate.kookeey.info:1000``

        Args:
            count:         number of proxy URLs
            country_code:  ISO-3166-1 alpha-2 (e.g. ``"JP"``) or ``"global"``
            sticky:        reuse the same session-ID (sticky IP)
            protocol:      ``"http"`` or ``"socks5"``
        """
        import random as _random

        auth = self.get_extraction_auth()
        username = auth.get("authname", "")
        password = auth.get("authpwd", "")
        if not username or not password:
            raise KookeeyAPIError(
                "extraction auth missing — check account security settings")

        session = str(_random.randint(10000000, 99999999))
        proxies: list[str] = []
        for _ in range(count):
            if not sticky:
                session = str(_random.randint(10000000, 99999999))
            proxies.append(
                "{}://{}-{}:{}-{}-{}@gate.kookeey.info:1000".format(
                    protocol, self.access_id, username, password,
                    country_code, session,
                )
            )
        print("[kookeey] generated {} extraction proxy URL(s) for {}".format(
            count, country_code))
        return proxies


if __name__ == "__main__":
    access_id = os.environ.get("KOOKEY_ACCESS_ID", "4419993")
    token = os.environ.get("KOOKEY_TOKEN", "")
    if not token:
        raise SystemExit("Set KOOKEY_TOKEN before running this example.")

    api = KookeeyAPI(access_id, token)
    proxies = api.fetch_proxies(count=5, geo_id=GEO_MAP["JP"], protocol="socks5h")
    for proxy in proxies:
        print(proxy)

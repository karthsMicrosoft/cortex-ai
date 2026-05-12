"""
Unit tests for app.services.url_ingest — Phase 5 / PR 5.2.

Covers the SSRF-hardened URL fetcher + readability extractor:
- URL scheme/format validation.
- DNS resolution + IP allow/deny (private, loopback, link-local incl. Azure IMDS).
- Redirect handling (max 3 hops, re-check every redirect target).
- Content-Length cap (5 MB).
- Content-Type allowlist (text/html, application/xhtml+xml).
- Timeout handling.
- Readability HTML → plain text extraction.
"""
from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import url_ingest
from app.services.url_ingest import (
    ContentTooLargeError,
    InvalidURLError,
    PrivateIPError,
    UnsupportedContentTypeError,
    UpstreamError,
    UpstreamTimeoutError,
    _extract_via_readability,
    _resolve_and_check_ip,
    _safe_fetch,
    _validate_url,
)


# ---------------------------------------------------------------------------
# 1. URL validation
# ---------------------------------------------------------------------------

class TestValidateURL:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "data:text/html,<h1>hi</h1>",
            "javascript:alert(1)",
            "gopher://example.com",
            "ssh://example.com",
        ],
    )
    def test_validate_url_rejects_non_http(self, bad_url: str):
        with pytest.raises(InvalidURLError):
            _validate_url(bad_url)

    @pytest.mark.parametrize(
        "bad_url",
        ["", "   ", "not-a-url", "http://", "https://", "://example.com", "http:///path"],
    )
    def test_validate_url_rejects_malformed(self, bad_url: str):
        with pytest.raises(InvalidURLError):
            _validate_url(bad_url)

    @pytest.mark.parametrize(
        "good_url",
        [
            "http://example.com",
            "https://example.com/foo",
            "https://nytimes.com/article/foo?x=1#frag",
        ],
    )
    def test_validate_url_accepts_http_https(self, good_url: str):
        host = _validate_url(good_url)
        assert host  # returns the hostname


# ---------------------------------------------------------------------------
# 2. DNS resolution + IP allow/deny
# ---------------------------------------------------------------------------

def _mk_getaddrinfo(*ips: str):
    """Build a fake socket.getaddrinfo that returns the supplied IPs."""

    def _fake(host, port, *args, **kwargs):
        out = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append((family, socket.SOCK_STREAM, 0, "", (ip, port or 0)))
        return out

    return _fake


class TestResolveAndCheckIP:
    def test_resolve_and_check_ip_rejects_private(self):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("10.0.0.1")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("internal.example.com")

    def test_resolve_and_check_ip_rejects_link_local_169_254_169_254(self):
        # Azure IMDS — must always be blocked.
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("169.254.169.254")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("metadata.example.com")

    def test_resolve_and_check_ip_rejects_loopback(self):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("127.0.0.1")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("localhost.example.com")

    def test_resolve_and_check_ip_rejects_loopback_ipv6(self):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("::1")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("v6loopback.example.com")

    def test_resolve_and_check_ip_rejects_link_local_ipv6(self):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("fe80::1")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("v6linklocal.example.com")

    @pytest.mark.parametrize(
        "private_ip",
        ["172.16.0.1", "192.168.1.1", "100.64.0.1", "0.0.0.0", "224.0.0.1"],
    )
    def test_resolve_and_check_ip_rejects_other_reserved(self, private_ip: str):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo(private_ip)):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("reserved.example.com")

    def test_resolve_and_check_ip_rejects_if_any_resolved_ip_private(self):
        # If any resolved address is private, block (DNS rebinding mitigation).
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8", "10.0.0.1")):
            with pytest.raises(PrivateIPError):
                _resolve_and_check_ip("mixed.example.com")

    def test_resolve_and_check_ip_allows_public(self):
        with patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")):
            ips = _resolve_and_check_ip("dns.google")
            assert "8.8.8.8" in ips

    def test_resolve_and_check_ip_resolution_failure_raises(self):
        def _boom(*a, **kw):
            raise socket.gaierror("no such host")
        with patch.object(socket, "getaddrinfo", _boom):
            with pytest.raises(InvalidURLError):
                _resolve_and_check_ip("nope.invalid")


# ---------------------------------------------------------------------------
# 3. _safe_fetch — redirects, size, type, timeout
# ---------------------------------------------------------------------------

def _mk_response(
    status_code: int = 200,
    *,
    headers: dict | None = None,
    content: bytes = b"<html><body><article><h1>T</h1><p>hello world</p></article></body></html>",
    url: str = "https://example.com/",
) -> httpx.Response:
    req = httpx.Request("GET", url)
    return httpx.Response(
        status_code=status_code,
        headers=headers or {"content-type": "text/html; charset=utf-8"},
        content=content,
        request=req,
    )


def _mk_async_client_returning(*responses: httpx.Response) -> MagicMock:
    """Build a fake httpx.AsyncClient class whose .get returns supplied responses
    in sequence (one per call)."""
    seq = list(responses)

    async def _get(url, *args, **kwargs):
        if not seq:
            raise AssertionError("ran out of mocked responses")
        return seq.pop(0)

    instance = MagicMock()
    instance.get = AsyncMock(side_effect=_get)
    instance.aclose = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)

    cls = MagicMock(return_value=instance)
    return cls


class TestSafeFetch:
    pytestmark = pytest.mark.asyncio

    async def test_safe_fetch_max_redirects(self):
        # 4 redirects → exceeds the 3-hop cap.
        r1 = _mk_response(302, headers={"location": "https://example.com/b"})
        r2 = _mk_response(302, headers={"location": "https://example.com/c"})
        r3 = _mk_response(302, headers={"location": "https://example.com/d"})
        r4 = _mk_response(302, headers={"location": "https://example.com/e"})
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1, r2, r3, r4)),
        ):
            with pytest.raises(UpstreamError):
                await _safe_fetch("https://example.com/a", max_redirects=3)

    async def test_safe_fetch_redirect_to_private_ip_blocked(self):
        # First request OK → redirects to a hostname that resolves to 127.0.0.1.
        r1 = _mk_response(302, headers={"location": "http://evil.example.com/"})

        # First DNS lookup (initial host) → public; second (redirect) → loopback.
        call_count = {"n": 0}

        def _ai(host, port, *args, **kwargs):
            call_count["n"] += 1
            ip = "8.8.8.8" if call_count["n"] == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port or 0))]

        with (
            patch.object(socket, "getaddrinfo", _ai),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            with pytest.raises(PrivateIPError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_content_length_too_large(self):
        # Content-Length declared > 5 MB → abort before reading body.
        r1 = _mk_response(
            200,
            headers={"content-type": "text/html", "content-length": str(10_000_000)},
        )
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            with pytest.raises(ContentTooLargeError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_body_overflow_aborts(self):
        # Content-Length missing but the body itself exceeds the cap.
        big = b"x" * (6 * 1024 * 1024)
        r1 = _mk_response(200, headers={"content-type": "text/html"}, content=big)
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            with pytest.raises(ContentTooLargeError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_content_type_not_html(self):
        r1 = _mk_response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"x":1}',
        )
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            with pytest.raises(UnsupportedContentTypeError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_content_type_xhtml_ok(self):
        r1 = _mk_response(
            200,
            headers={"content-type": "application/xhtml+xml; charset=utf-8"},
        )
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            html, final_url = await _safe_fetch("https://example.com/")
            assert "hello world" in html
            assert final_url == "https://example.com/"

    async def test_safe_fetch_timeout(self):
        async def _boom(*a, **kw):
            raise httpx.TimeoutException("timeout")

        instance = MagicMock()
        instance.get = AsyncMock(side_effect=_boom)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        cls = MagicMock(return_value=instance)

        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", cls),
        ):
            with pytest.raises(UpstreamTimeoutError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_non_2xx_raises_upstream_error(self):
        r1 = _mk_response(500, headers={"content-type": "text/html"}, content=b"oops")
        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", _mk_async_client_returning(r1)),
        ):
            with pytest.raises(UpstreamError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_network_error_raises_upstream_error(self):
        async def _boom(*a, **kw):
            raise httpx.ConnectError("dns fail")

        instance = MagicMock()
        instance.get = AsyncMock(side_effect=_boom)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        cls = MagicMock(return_value=instance)

        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", cls),
        ):
            with pytest.raises(UpstreamError):
                await _safe_fetch("https://example.com/")

    async def test_safe_fetch_user_agent_set(self):
        r1 = _mk_response(200)
        captured: dict = {}

        async def _get(url, *args, **kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return r1

        instance = MagicMock()
        instance.get = AsyncMock(side_effect=_get)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        cls = MagicMock(return_value=instance)

        with (
            patch.object(socket, "getaddrinfo", _mk_getaddrinfo("8.8.8.8")),
            patch.object(httpx, "AsyncClient", cls),
        ):
            await _safe_fetch("https://example.com/")

        ua = captured["headers"].get("User-Agent") or captured["headers"].get("user-agent")
        assert ua and "Cortex" in ua


# ---------------------------------------------------------------------------
# 4. Readability extraction
# ---------------------------------------------------------------------------

class TestExtractViaReadability:
    def test_extract_via_readability_strips_html(self):
        html = """
        <html><head><title>My Article</title></head>
        <body>
          <nav>Home | About</nav>
          <article>
            <h1>My Article</h1>
            <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
            <p>Second paragraph with <a href="/x">a link</a>.</p>
          </article>
          <footer>Copyright</footer>
        </body></html>
        """
        title, text = _extract_via_readability(html)
        assert "My Article" in title
        assert "Lorem ipsum" in text
        assert "<p>" not in text
        assert "<a" not in text
        assert "Second paragraph" in text

    def test_extract_via_readability_empty_input(self):
        with pytest.raises(url_ingest.ExtractionEmptyError):
            _extract_via_readability("")

    def test_extract_via_readability_empty_body(self):
        with pytest.raises(url_ingest.ExtractionEmptyError):
            _extract_via_readability("<html><body></body></html>")

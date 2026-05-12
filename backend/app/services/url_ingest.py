"""
SSRF-hardened URL fetcher + readability extractor (Phase 5 / PR 5.2).

Public entry point:
    fetch_and_extract(url) -> ExtractedPage

Defence-in-depth pipeline:
    1. _validate_url        — http/https only, syntactically valid.
    2. _resolve_and_check_ip— resolve host, reject any private/loopback/
                              link-local/multicast/reserved IP (incl. Azure
                              IMDS at 169.254.169.254). Re-checked at every
                              redirect target (DNS-rebinding mitigation).
    3. _safe_fetch          — manual redirect handling capped at 3 hops, with
                              Content-Length cap (5 MB), streamed-body cap,
                              Content-Type allowlist, 10 s total timeout.
    4. _extract_via_readability — readability-lxml + BeautifulSoup → plain
                              text. Raises ExtractionEmptyError when the
                              extracted body is meaningfully empty.

All exceptions are explicit and map 1:1 to HTTP status codes by the
import_url router:
    InvalidURLError              → 400
    PrivateIPError               → 403
    ContentTooLargeError         → 413
    UnsupportedContentTypeError  → 415
    ExtractionEmptyError         → 422
    UpstreamError                → 502
    UpstreamTimeoutError         → 504
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import TypedDict
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types + exceptions
# ---------------------------------------------------------------------------

class ExtractedPage(TypedDict):
    title: str
    content: str
    final_url: str


class URLIngestError(Exception):
    """Base class for url_ingest failures."""


class InvalidURLError(URLIngestError):
    """URL is malformed or not http/https."""


class PrivateIPError(URLIngestError):
    """URL host resolves to a private/internal/reserved IP — SSRF block."""


class ContentTooLargeError(URLIngestError):
    """Response body exceeds the 5 MB cap."""


class UnsupportedContentTypeError(URLIngestError):
    """Response Content-Type is not text/html or application/xhtml+xml."""


class ExtractionEmptyError(URLIngestError):
    """Readability could not extract any meaningful content."""


class UpstreamError(URLIngestError):
    """Network error / non-2xx status / too many redirects."""


class UpstreamTimeoutError(URLIngestError):
    """Upstream server took too long to respond."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 3
_MAX_BYTES = 5 * 1024 * 1024            # 5 MB
_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "Cortex/1.0 (+https://cortexks.app)"
_ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}

# Hard-coded extra block: Azure / GCP / AWS metadata endpoint. ipaddress'
# is_link_local already covers 169.254.0.0/16, but be paranoid and fail loud.
_BLOCKED_LITERAL_IPS = {"169.254.169.254"}


# ---------------------------------------------------------------------------
# 1. URL validation
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> str:
    """Validate *url* and return the (lowercased) hostname.

    Rejects anything that is not a syntactically valid http(s):// URL with a
    non-empty hostname.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise InvalidURLError("URL is empty")

    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise InvalidURLError(f"URL parse failed: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidURLError(f"Unsupported scheme: {scheme or '<empty>'}")

    host = (parsed.hostname or "").strip()
    if not host:
        raise InvalidURLError("URL is missing a hostname")

    return host.lower()


# ---------------------------------------------------------------------------
# 2. DNS resolution + IP allow/deny
# ---------------------------------------------------------------------------

def _is_blocked_ip(ip_str: str) -> bool:
    """True iff *ip_str* is in any blocked range."""
    if ip_str in _BLOCKED_LITERAL_IPS:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True

    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_reserved
    ):
        return True

    # CGN range (100.64.0.0/10) is not flagged as private by the stdlib until
    # 3.13 in some builds — explicit guard.
    if isinstance(addr, ipaddress.IPv4Address):
        cgn = ipaddress.ip_network("100.64.0.0/10")
        if addr in cgn:
            return True
        if str(addr) == "255.255.255.255":
            return True

    return False


def _resolve_and_check_ip(host: str) -> list[str]:
    """Resolve *host* to all IPs (A + AAAA) and reject if any is non-public.

    Returns the list of resolved IP strings on success.
    Raises:
        InvalidURLError — DNS resolution failed.
        PrivateIPError  — at least one resolved IP is private/internal.
    """
    # Short-circuit: if the host parses as a literal IP, run the same check
    # without going through DNS. This catches `http://169.254.169.254/`.
    try:
        ip_literal = ipaddress.ip_address(host)
    except ValueError:
        ip_literal = None

    if ip_literal is not None:
        if _is_blocked_ip(str(ip_literal)):
            raise PrivateIPError(f"Blocked IP literal: {host}")
        return [str(ip_literal)]

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise InvalidURLError(f"DNS resolution failed for {host}: {exc}") from exc

    ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        # Strip IPv6 zone-id (e.g. fe80::1%eth0) before parsing.
        if "%" in ip:
            ip = ip.split("%", 1)[0]
        ips.append(ip)

    if not ips:
        raise InvalidURLError(f"DNS returned no addresses for {host}")

    for ip in ips:
        if _is_blocked_ip(ip):
            raise PrivateIPError(f"Host {host} resolves to blocked IP {ip}")

    return ips


# ---------------------------------------------------------------------------
# 3. Safe fetch with manual redirect handling
# ---------------------------------------------------------------------------

def _content_type_allowed(header_value: str | None) -> bool:
    if not header_value:
        return False
    main = header_value.split(";", 1)[0].strip().lower()
    return main in _ALLOWED_CONTENT_TYPES


async def _safe_fetch(url: str, max_redirects: int = _MAX_REDIRECTS) -> tuple[str, str]:
    """Fetch *url*, following up to *max_redirects* redirects manually.

    Re-validates the URL + re-resolves DNS + re-checks IPs at every hop.
    Returns ``(html_text, final_url)``.

    Raises one of the URLIngestError subclasses on any failure.
    """
    current = url
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=timeout
        ) as http:
            for hop in range(max_redirects + 1):
                host = _validate_url(current)
                _resolve_and_check_ip(host)

                try:
                    resp = await http.get(current, headers=headers)
                except httpx.TimeoutException as exc:
                    raise UpstreamTimeoutError(
                        f"Timeout fetching {current}: {exc}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise UpstreamError(
                        f"Network error fetching {current}: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc

                # Redirect?
                if 300 <= resp.status_code < 400 and "location" in {
                    k.lower() for k in resp.headers.keys()
                }:
                    if hop >= max_redirects:
                        raise UpstreamError(
                            f"Too many redirects (>{max_redirects}) starting at {url}"
                        )
                    location = resp.headers.get("location") or resp.headers.get(
                        "Location"
                    )
                    if not location:
                        raise UpstreamError(
                            f"Redirect from {current} missing Location header"
                        )
                    current = urljoin(current, location)
                    continue

                # Non-redirect: must be 2xx.
                if not (200 <= resp.status_code < 300):
                    raise UpstreamError(
                        f"Upstream returned {resp.status_code} for {current}"
                    )

                # Content-Length pre-check.
                cl_header = resp.headers.get("content-length")
                if cl_header is not None:
                    try:
                        cl = int(cl_header)
                    except ValueError:
                        cl = None
                    if cl is not None and cl > _MAX_BYTES:
                        raise ContentTooLargeError(
                            f"Content-Length {cl} exceeds {_MAX_BYTES} bytes"
                        )

                # Content-Type allowlist.
                ct = resp.headers.get("content-type")
                if not _content_type_allowed(ct):
                    raise UnsupportedContentTypeError(
                        f"Unsupported Content-Type: {ct!r}"
                    )

                # Body size cap (defensive — Content-Length may have been absent
                # or wrong).
                body = resp.content
                if len(body) > _MAX_BYTES:
                    raise ContentTooLargeError(
                        f"Response body {len(body)} bytes exceeds {_MAX_BYTES}"
                    )

                # Decode using httpx's charset detection.
                try:
                    text = resp.text
                except (UnicodeDecodeError, LookupError):
                    text = body.decode("utf-8", errors="replace")

                return text, current

    except URLIngestError:
        raise
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{type(exc).__name__}: {exc}") from exc

    # Should be unreachable — the loop either returns or raises.
    raise UpstreamError("Fetch loop exited unexpectedly")


# ---------------------------------------------------------------------------
# 4. Readability extraction
# ---------------------------------------------------------------------------

def _extract_via_readability(html: str) -> tuple[str, str]:
    """Extract (title, plain_text) from *html* using readability-lxml + BS4.

    Raises ExtractionEmptyError when the extracted body is empty after
    whitespace normalisation.
    """
    if not html or not html.strip():
        raise ExtractionEmptyError("Empty input HTML")

    # readability-lxml is the canonical port of arc90 readability.
    from readability import Document  # type: ignore[import-not-found]
    from bs4 import BeautifulSoup  # type: ignore[import-not-found]

    try:
        doc = Document(html)
        title = (doc.short_title() or "").strip() or (doc.title() or "").strip()
        summary_html = doc.summary(html_partial=True) or ""
    except Exception as exc:  # noqa: BLE001
        # readability raises a variety of lxml errors on broken input.
        raise ExtractionEmptyError(f"Readability failed: {exc}") from exc

    soup = BeautifulSoup(summary_html, "lxml")
    # Strip script/style outright before extracting text.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n").strip()
    # Collapse runs of blank lines.
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    if not text:
        raise ExtractionEmptyError("No textual content after extraction")

    if not title:
        # Fallback: first non-empty line of text, capped at 120 chars.
        title = text.splitlines()[0][:120]

    return title, text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def fetch_and_extract(url: str) -> ExtractedPage:
    """Validate, fetch, and extract *url*. Returns ExtractedPage.

    Raises one of the URLIngestError subclasses on any failure.
    """
    # Pre-flight validation of the user-supplied URL: scheme + host shape +
    # immediate IP-literal SSRF check (so `http://169.254.169.254/` is rejected
    # before we even open a socket).
    host = _validate_url(url)
    _resolve_and_check_ip(host)

    html, final_url = await _safe_fetch(url)
    title, content = _extract_via_readability(html)
    return ExtractedPage(title=title, content=content, final_url=final_url)

"""Content-Security-Policy middleware for the backend.

Round 20 / PR delta — DECISIONS § 22v hardening.

The backend serves only JSON; there are no HTML documents, no inline
scripts, no embedded resources. The strictest possible CSP is therefore
appropriate: ``default-src 'none'`` blocks everything and
``frame-ancestors 'none'`` prevents any page from embedding API
responses in an iframe (defence-in-depth against clickjacking even
though there is no UI to click).

Two additional hardening headers are attached as belt-and-braces:

* ``X-Content-Type-Options: nosniff`` — prevents MIME sniffing.
* ``Referrer-Policy: no-referrer`` — never leak API URLs in Referer.

Both are only set if the response does not already carry the header,
so downstream handlers can override if they have a good reason to.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CSP_VALUE = "default-src 'none'; frame-ancestors 'none'"


class StrictCspMiddleware(BaseHTTPMiddleware):
    """Attach a strict Content-Security-Policy to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP_VALUE
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

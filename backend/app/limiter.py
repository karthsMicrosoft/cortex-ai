"""
Shared slowapi rate-limiter instance.

Defined here (not in main.py) so that API routers can import it without
causing a circular import via app.main.

main.py attaches this instance to app.state and registers the middleware.
API routers import it directly to apply @limiter.limit() decorators.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi import Request


def _get_user_or_ip(request: Request) -> str:
    """
    Key function for slowapi: prefer authenticated user identity over raw IP
    so the per-user rate limit applies correctly to authenticated requests.
    Falls back to remote address for unauthenticated requests.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_or_ip, default_limits=["100/minute"])

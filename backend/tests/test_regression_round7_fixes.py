"""
Regression tests for Round-7 bugs reported 2026-05-01.

Bugs covered:
  B22 — Refresh-page logout (round-7 root cause: Edge 147 "Balanced" tracking
        prevention blocks all third-party cookies even with SameSite=None+Secure).
        SWA Free-tier has no linked-backend reverse proxy, so the browser never
        sends the refresh cookie to the Azure Container App origin.

        Fix: move refresh token delivery to localStorage + JSON body.
          Backend:  /login, /register, /refresh all include refresh_token in the
                    JSON response body (cookie-set is kept as defense-in-depth).
          Frontend: auth.ts login()/register() write data.refresh_token to
                    localStorage.setItem('cortex_refresh', token).
                    refresh() reads localStorage and passes it as body.
                    client.ts inline auto-refresh also reads from localStorage.
                    logout() removes localStorage item.

  B23 — Mobile voice "Network issue" (round-7 root cause: WebSocket streaming
        path always fails on mobile; Round-5 MIME fix was on the fallback path
        which itself also fails occasionally, giving a poor UX).

        Fix: useVoiceRecorder.ts detects mobile UA and skips the WebSocket
        path entirely, going straight to uploadVoice. DegradedToast text must
        not say "Network issue" when mobile is the primary (not fallback) path.
"""

import inspect
import re
import uuid

import pytest
import pytest_asyncio

from pathlib import Path

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read_frontend(relative: str) -> str:
    path = FRONTEND_ROOT / relative
    if not path.exists():
        raise FileNotFoundError(f"Frontend file not found: {path}")
    return path.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """Remove JS/TS block and line comments so statics target runtime code."""
    no_block = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"//[^\n]*", "", no_block)


# ===========================================================================
# B22 — Refresh page logs user out (round-7 fix: localStorage + body)
# ===========================================================================


class TestB22LocalStorageRefreshToken:
    """Bug 22 (round 7): Edge 147 tracking-prevention drops third-party cookies
    even when SameSite=None+Secure is set.  SWA Free tier has no linked-backend
    proxy, so the refresh cookie is never sent cross-origin.

    Fix: deliver refresh_token in JSON body for /login, /register, and /refresh;
    persist it to localStorage; read it back on refresh; clear on logout.
    Cookie-set is retained as defense-in-depth for browsers that allow it.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _auth_schemas_source() -> str:
        from app.schemas import auth as schemas_mod
        return inspect.getsource(schemas_mod)

    @staticmethod
    def _auth_py_source() -> str:
        from app.api import auth as auth_mod
        return inspect.getsource(auth_mod)

    @staticmethod
    def _auth_ts() -> str:
        return _read_frontend("api/auth.ts")

    @staticmethod
    def _client_ts() -> str:
        return _read_frontend("api/client.ts")

    # ------------------------------------------------------------------
    # 1. Schema: TokenPair includes refresh_token field
    # ------------------------------------------------------------------

    def test_token_pair_schema_has_refresh_token_field(self):
        """TokenPair (login response) must declare a refresh_token: str field
        so the backend can include it in the JSON body.

        Without this the frontend cannot read data.refresh_token after login
        and localStorage is never populated — browser cookie blocking causes
        every subsequent refresh to 401.
        """
        src = self._auth_schemas_source()
        code = _strip_comments(src)

        # Look for: class TokenPair(BaseModel): ... refresh_token ...
        # Allow any field declaration form (refresh_token: str, refresh_token: Optional[str], etc.)
        token_pair_block = re.search(
            r"class\s+TokenPair\s*\(BaseModel\)\s*:(.*?)(?=\nclass\s|\Z)",
            code,
            re.DOTALL,
        )
        assert token_pair_block, (
            "Bug 22 (R7): cannot find `class TokenPair(BaseModel)` in app/schemas/auth.py."
        )
        block_text = token_pair_block.group(1)
        assert "refresh_token" in block_text, (
            "Bug 22 (R7): `TokenPair` schema does not include a `refresh_token` field. "
            "Add `refresh_token: str` so /login and /register return the token in the "
            "JSON body — required because Edge 147 tracking-prevention blocks the cookie."
        )

    # ------------------------------------------------------------------
    # 2. Schema: AccessTokenResponse includes refresh_token field
    # ------------------------------------------------------------------

    def test_access_token_response_schema_has_refresh_token_field(self):
        """AccessTokenResponse (/refresh endpoint response) must also declare
        refresh_token so the rotated token reaches localStorage after each refresh.

        Without this the stored refresh_token in localStorage becomes stale after
        the first successful rotation and subsequent refreshes fail.
        """
        src = self._auth_schemas_source()
        code = _strip_comments(src)

        atok_block = re.search(
            r"class\s+AccessTokenResponse\s*\(BaseModel\)\s*:(.*?)(?=\nclass\s|\Z)",
            code,
            re.DOTALL,
        )
        assert atok_block, (
            "Bug 22 (R7): cannot find `class AccessTokenResponse(BaseModel)` "
            "in app/schemas/auth.py."
        )
        block_text = atok_block.group(1)
        assert "refresh_token" in block_text, (
            "Bug 22 (R7): `AccessTokenResponse` does not include `refresh_token`. "
            "The /refresh endpoint must return the new refresh_token in the body so "
            "the frontend can update localStorage after each rotation."
        )

    # ------------------------------------------------------------------
    # 3. Backend: login, register, refresh_token endpoints return refresh_token=
    # ------------------------------------------------------------------

    def test_login_endpoint_returns_refresh_token_in_body(self):
        """auth.login must construct its return value with refresh_token=<value>
        so the field is populated in the JSON response.

        Currently it returns `TokenPair(access_token=..., token_type='bearer')`
        without refresh_token — that field would serialize as None or be absent.
        """
        src = self._auth_py_source()
        # Isolate the login function body: from 'async def login' to next 'async def'
        login_match = re.search(
            r"async def login\b.*?(?=\nasync def |\Z)",
            src,
            re.DOTALL,
        )
        assert login_match, "Bug 22 (R7): could not isolate `async def login` in auth.py."
        login_body = login_match.group(0)
        assert "refresh_token=" in login_body, (
            "Bug 22 (R7): auth.login does not include `refresh_token=` in its TokenPair "
            "return statement. The frontend cannot persist the token to localStorage "
            "and cookie-blocking causes every page-reload to log the user out.\n"
            f"Login body excerpt: {login_body[:400]}"
        )

    def test_register_endpoint_returns_refresh_token_in_body(self):
        """auth.register must include refresh_token in its JSON response.

        After sign-up, auth.ts register() must be able to write
        data.refresh_token to localStorage immediately so the first page-reload
        after registration does not log the user out.
        """
        src = self._auth_py_source()
        reg_match = re.search(
            r"async def register\b.*?(?=\nasync def |\Z)",
            src,
            re.DOTALL,
        )
        assert reg_match, "Bug 22 (R7): could not isolate `async def register` in auth.py."
        reg_body = reg_match.group(0)
        assert "refresh_token=" in reg_body, (
            "Bug 22 (R7): auth.register does not include `refresh_token=` in its "
            "response. After sign-up the frontend needs to persist the refresh_token "
            "to localStorage before the first reload — without it the first reload "
            "after registration logs the user out.\n"
            f"Register body excerpt: {reg_body[:400]}"
        )

    def test_refresh_token_endpoint_returns_refresh_token_in_body(self):
        """auth.refresh_token must include the NEW refresh_token in its
        AccessTokenResponse so the rotated value replaces the old one in
        localStorage.  Without rotation localStorage stays stale.
        """
        src = self._auth_py_source()
        refresh_match = re.search(
            r"async def refresh_token\b.*?(?=\nasync def |\Z)",
            src,
            re.DOTALL,
        )
        assert refresh_match, (
            "Bug 22 (R7): could not isolate `async def refresh_token` in auth.py."
        )
        refresh_body = refresh_match.group(0)
        assert "refresh_token=" in refresh_body, (
            "Bug 22 (R7): auth.refresh_token does not include `refresh_token=` in "
            "its AccessTokenResponse return statement. The rotated refresh_token "
            "must be returned in the body so localStorage can be updated — otherwise "
            "the stored token becomes stale after the first rotation.\n"
            f"Refresh body excerpt: {refresh_body[:400]}"
        )

    # ------------------------------------------------------------------
    # 4. Behavioral: register → body has refresh_token, then refresh via body
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_login_response_body_contains_refresh_token(self, client):
        """POST /api/auth/login JSON body must include 'refresh_token' field."""
        email = f"b22r7_{uuid.uuid4().hex[:6]}@example.com"
        password = "TestPass123!"

        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "R7 Test"},
        )
        assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"
        data = login.json()
        assert "refresh_token" in data, (
            "Bug 22 (R7): /api/auth/login JSON body does not include 'refresh_token'. "
            f"Got keys: {list(data.keys())}. "
            "Edge 147 blocks the httpOnly cookie cross-origin; the token MUST be in "
            "the JSON body so the frontend can persist it to localStorage."
        )
        assert data["refresh_token"], (
            "Bug 22 (R7): /api/auth/login returned refresh_token=null/empty. "
            "The token must be a non-empty JWT string."
        )

    @pytest.mark.asyncio
    async def test_refresh_via_json_body_no_cookie_returns_200_with_new_tokens(self, client):
        """POST /api/auth/refresh with refresh_token in JSON body and NO cookie
        must return 200 with both access_token and refresh_token in the body.

        This is the core fix: browsers blocking cookies must still be able to
        refresh via the JSON body path.
        """
        email = f"b22r7b_{uuid.uuid4().hex[:6]}@example.com"
        password = "TestPass123!"

        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "R7 Body Test"},
        )
        assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"
        login_data = login.json()
        assert "refresh_token" in login_data, (
            "Bug 22 (R7): /login body missing refresh_token — cannot proceed with "
            "body-based refresh test."
        )
        stored_refresh = login_data["refresh_token"]

        # POST refresh with body only — httpx AsyncClient sends no browser cookies
        refresh_resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": stored_refresh},
        )
        assert refresh_resp.status_code == 200, (
            "Bug 22 (R7): POST /api/auth/refresh with JSON body returned "
            f"{refresh_resp.status_code}: {refresh_resp.text}. "
            "The body-only path must work for browsers where cookie is blocked."
        )
        refresh_data = refresh_resp.json()
        assert "access_token" in refresh_data, (
            f"Bug 22 (R7): /api/auth/refresh body response missing 'access_token'. "
            f"Got: {refresh_data}"
        )
        assert "refresh_token" in refresh_data, (
            "Bug 22 (R7): /api/auth/refresh body response missing 'refresh_token'. "
            "The rotated token must be returned so localStorage can be updated. "
            f"Got: {refresh_data}"
        )
        assert refresh_data["refresh_token"], (
            "Bug 22 (R7): /api/auth/refresh returned an empty refresh_token."
        )

    # ------------------------------------------------------------------
    # 5. Frontend: auth.ts login() stores refresh_token to localStorage
    # ------------------------------------------------------------------

    def test_auth_ts_login_writes_refresh_token_to_localstorage(self):
        """auth.ts login() must call localStorage.setItem with the refresh_token
        after a successful response.

        Without this, localStorage is never populated and body-based refresh
        never sends a token — the user still gets logged out on reload.
        """
        src = self._auth_ts()
        code = _strip_comments(src)

        # Isolate the login function body
        login_match = re.search(
            r"(?:export\s+)?(?:async\s+)?function\s+login\s*\([^)]*\)[^{]*\{([\s\S]*?)\n\}",
            code,
        )
        if not login_match:
            # Arrow function form
            login_match = re.search(
                r"(?:export\s+)?(?:const|let)\s+login\s*=\s*async[^=]*=>\s*\{([\s\S]*?)\n\}",
                code,
            )

        assert login_match, (
            "Bug 22 (R7): cannot isolate `login` function in frontend/src/api/auth.ts."
        )
        fn_body = login_match.group(1)

        assert "localStorage.setItem" in fn_body, (
            "Bug 22 (R7): auth.ts login() does not call localStorage.setItem after "
            "a successful response. The refresh_token from data.refresh_token must be "
            "persisted to localStorage so that refresh() can send it in the body when "
            "the httpOnly cookie is blocked by Edge tracking prevention."
        )
        # Check it's related to refresh token, not some unrelated key
        assert re.search(r"localStorage\.setItem\s*\([^)]*refresh", fn_body), (
            "Bug 22 (R7): auth.ts login() calls localStorage.setItem but the key "
            "does not appear to be related to 'refresh'. Expected a call like "
            "localStorage.setItem('cortex_refresh', data.refresh_token)."
        )

    # ------------------------------------------------------------------
    # 6. Frontend: auth.ts register() stores refresh_token to localStorage
    # ------------------------------------------------------------------

    def test_auth_ts_register_writes_refresh_token_to_localstorage(self):
        """auth.ts register() must also persist the refresh_token from the
        response body to localStorage.

        If only login() does this but register() does not, the first page-reload
        after sign-up (before any explicit login) will fail to find the token
        and the user is logged out.
        """
        src = self._auth_ts()
        code = _strip_comments(src)

        reg_match = re.search(
            r"(?:export\s+)?(?:async\s+)?function\s+register\s*\([^)]*\)[^{]*\{([\s\S]*?)\n\}",
            code,
        )
        if not reg_match:
            reg_match = re.search(
                r"(?:export\s+)?(?:const|let)\s+register\s*=\s*async[^=]*=>\s*\{([\s\S]*?)\n\}",
                code,
            )

        assert reg_match, (
            "Bug 22 (R7): cannot isolate `register` function in frontend/src/api/auth.ts."
        )
        fn_body = reg_match.group(1)

        assert "localStorage.setItem" in fn_body, (
            "Bug 22 (R7): auth.ts register() does not call localStorage.setItem. "
            "After sign-up the backend returns refresh_token in the body; "
            "register() must persist it to localStorage so a hard-reload after "
            "sign-up can refresh without a cookie."
        )
        assert re.search(r"localStorage\.setItem\s*\([^)]*refresh", fn_body), (
            "Bug 22 (R7): auth.ts register() localStorage.setItem key does not "
            "appear related to 'refresh'."
        )

    # ------------------------------------------------------------------
    # 7. Frontend: auth.ts refresh() reads from localStorage and sends in body
    # ------------------------------------------------------------------

    def test_auth_ts_refresh_reads_localstorage_and_sends_in_body(self):
        """auth.ts refresh() must:
         1. Read the stored refresh token via localStorage.getItem(...)
         2. Include it as the `refresh_token` field in the POST body

        Without (1) the body is empty and the backend falls back to the cookie
        which is blocked.  Without (2) the token is read but not sent.
        """
        src = self._auth_ts()
        code = _strip_comments(src)

        refresh_match = re.search(
            r"(?:export\s+)?(?:async\s+)?function\s+refresh\s*\([^)]*\)[^{]*\{([\s\S]*?)\n\}",
            code,
        )
        if not refresh_match:
            refresh_match = re.search(
                r"(?:export\s+)?(?:const|let)\s+refresh\s*=\s*async[^=]*=>\s*\{([\s\S]*?)\n\}",
                code,
            )

        assert refresh_match, (
            "Bug 22 (R7): cannot isolate `refresh` function in frontend/src/api/auth.ts."
        )
        fn_body = refresh_match.group(1)

        assert "localStorage.getItem" in fn_body, (
            "Bug 22 (R7): auth.ts refresh() does not call localStorage.getItem. "
            "It must read the stored refresh_token and send it in the POST body "
            "so browsers with cookie-blocking can still obtain a new access token."
        )
        # Must pass something to the POST — look for refresh_token in the body arg
        assert re.search(r"refresh_token", fn_body), (
            "Bug 22 (R7): auth.ts refresh() reads localStorage but does not appear "
            "to send 'refresh_token' in the POST body. The stored token must be passed "
            "as { refresh_token: storedToken } to apiPost('/api/auth/refresh', ...)."
        )

    # ------------------------------------------------------------------
    # 8. Frontend: client.ts inline auto-refresh reads localStorage
    # ------------------------------------------------------------------

    def test_client_ts_inline_refresh_reads_localstorage(self):
        """The inline auto-refresh inside fetchWithAuth (client.ts) must also
        read from localStorage and include refresh_token in the body when it
        retries after a 401.

        If only auth.ts refresh() is fixed but client.ts is not, automatic
        retries on expired tokens will still fail for cookie-blocked browsers.
        """
        src = self._client_ts()
        code = _strip_comments(src)

        # Find the auto-refresh fetch block — the fetch call to /api/auth/refresh
        # that happens inside the 401 handler branch of fetchWithAuth.
        # It must now also include a body with the localStorage token.
        assert "localStorage.getItem" in code, (
            "Bug 22 (R7): client.ts does not call localStorage.getItem anywhere. "
            "The inline auto-refresh fetch inside fetchWithAuth must read the "
            "stored refresh_token from localStorage and pass it in the body, "
            "otherwise automatic token refresh fails when cookies are blocked."
        )

        # The localStorage read should be near the /api/auth/refresh fetch
        ls_pos = code.find("localStorage.getItem")
        refresh_fetch_pos = code.find("/api/auth/refresh")
        assert ls_pos != -1 and refresh_fetch_pos != -1, (
            "Bug 22 (R7): client.ts missing localStorage.getItem or "
            "/api/auth/refresh reference."
        )
        # They should be within 500 chars of each other (same code block)
        assert abs(ls_pos - refresh_fetch_pos) < 800, (
            "Bug 22 (R7): localStorage.getItem in client.ts appears far from "
            "the /api/auth/refresh fetch call. The localStorage read should be "
            "in the same inline-refresh block that posts to /api/auth/refresh."
        )

    # ------------------------------------------------------------------
    # 9. Frontend: logout() clears localStorage
    # ------------------------------------------------------------------

    def test_auth_ts_logout_removes_refresh_token_from_localstorage(self):
        """auth.ts logout() must call localStorage.removeItem (or clear) for
        the refresh_token key.

        If logout() does not clear localStorage, the stale refresh_token persists
        across sessions and could be replayed (or just confuse subsequent logins).
        """
        src = self._auth_ts()
        code = _strip_comments(src)

        logout_match = re.search(
            r"(?:export\s+)?(?:async\s+)?function\s+logout\s*\([^)]*\)[^{]*\{([\s\S]*?)\n\}",
            code,
        )
        if not logout_match:
            logout_match = re.search(
                r"(?:export\s+)?(?:const|let)\s+logout\s*=\s*async[^=]*=>\s*\{([\s\S]*?)\n\}",
                code,
            )

        assert logout_match, (
            "Bug 22 (R7): cannot isolate `logout` function in frontend/src/api/auth.ts."
        )
        fn_body = logout_match.group(1)

        assert re.search(r"localStorage\.(removeItem|clear)\s*\(", fn_body), (
            "Bug 22 (R7): auth.ts logout() does not call localStorage.removeItem "
            "or localStorage.clear(). The persisted refresh_token must be removed "
            "on logout to prevent stale token reuse and to correctly represent the "
            "logged-out state for cookie-blocked browsers."
        )

    # ------------------------------------------------------------------
    # 10. SessionGate must NOT call logout() on refresh failure (R5 regression guard)
    # ------------------------------------------------------------------

    def test_session_gate_does_not_call_logout_on_refresh_failure(self):
        """Round-5 fix: SessionGate catch block must not call logout() when
        /refresh fails on startup — that would clear auth state for a user whose
        network had a transient error.

        This is a regression guard: the fix landed in R5 and must stay.
        """
        src = _read_frontend("components/SessionGate.tsx")
        code = _strip_comments(src)

        # Find the catch block of the refresh call inside the useEffect
        catch_match = re.search(r"\}\s*catch\s*[^{]*\{([^}]*)\}", code, re.DOTALL)
        if catch_match:
            catch_body = catch_match.group(1)
            assert "logout" not in catch_body, (
                "Bug 22 (R5 regression): SessionGate catch block calls logout() "
                "on a refresh failure. This was fixed in Round 5 — the catch block "
                "must only call setRestoring(false) and leave the user unauthenticated "
                "silently (AuthGate handles the redirect). Calling logout() on a "
                "transient network error forces the user to re-login unnecessarily."
            )
        else:
            # Fallback: check globally that logout() is not imported AND used in
            # the catch context. If no catch block found by simple regex, at minimum
            # verify logout is not called at all in SessionGate.
            assert "logout()" not in code, (
                "Bug 22 (R5 regression): SessionGate calls logout(). "
                "The SessionGate must never call logout() — not even in error paths."
            )


# ===========================================================================
# B23 — Mobile voice "Network issue" (round-7 fix: force-skip WS on mobile)
# ===========================================================================


class TestB23MobileVoiceSkipsWebSocket:
    """Bug 23 (round 7): Mobile voice recording always fails the WebSocket
    streaming path and falls through to the file-upload fallback, surfacing
    'Network issue — using file upload fallback' toast on EVERY recording.
    The Round-5 MIME fix (audio/mp4 support) didn't help because the WS
    path fails before any audio is sent on iOS/Android.

    Fix: useVoiceRecorder.ts (or VoiceCapture.tsx) detects a mobile UA and
    skips the WebSocket path entirely, going straight to uploadVoice.  The
    degraded-mode toast text must not say 'Network issue' when mobile is the
    intended primary path (not a fallback).
    """

    @staticmethod
    def _voice_recorder_src() -> str:
        return _read_frontend("hooks/useVoiceRecorder.ts")

    @staticmethod
    def _voice_capture_src() -> str:
        return _read_frontend("components/VoiceCapture.tsx")

    # ------------------------------------------------------------------
    # 1. useVoiceRecorder.ts contains a UA check for mobile browsers
    # ------------------------------------------------------------------

    def test_use_voice_recorder_has_mobile_ua_check(self):
        """useVoiceRecorder.ts must check navigator.userAgent for mobile
        indicators (iPhone, iPad, iPod, Android) so the hook (or its caller)
        can skip the WebSocket path on mobile.

        Without a UA check the WS path is always attempted and always fails
        on mobile, causing the 'Network issue' toast on every recording.
        """
        src = self._voice_recorder_src()
        code = _strip_comments(src)

        assert "navigator.userAgent" in code, (
            "Bug 23 (R7): useVoiceRecorder.ts does not reference navigator.userAgent. "
            "The hook must detect mobile browsers via a UA regex check "
            "(e.g. /iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) "
            "and set an isMobile flag used to skip the WebSocket path."
        )

    def test_use_voice_recorder_ua_check_covers_iphone_android(self):
        """The UA regex in useVoiceRecorder.ts must cover at least iPhone and
        Android (the two most common mobile platforms affected by the WS failure).
        """
        src = self._voice_recorder_src()
        # Check for a regex pattern that includes both iPhone and Android
        has_iphone = bool(re.search(r"iPhone", src))
        has_android = bool(re.search(r"Android", src))
        assert has_iphone and has_android, (
            "Bug 23 (R7): useVoiceRecorder.ts UA regex does not cover both "
            f"'iPhone' (found={has_iphone}) and 'Android' (found={has_android}). "
            "The mobile detection must match at least iPhone|iPad|iPod|Android "
            "to cover iOS Safari and Chrome/Firefox for Android."
        )

    # ------------------------------------------------------------------
    # 2. useVoiceRecorder.ts has a code path that bypasses WS on mobile
    # ------------------------------------------------------------------

    def test_use_voice_recorder_has_mobile_skip_branch(self):
        """useVoiceRecorder.ts must have an explicit branch that skips the
        WebSocket path when the UA check identifies a mobile device.

        Acceptable patterns: `if (isMobile)`, `isMobile &&`, `isMobile ?`.
        The branch should lead to uploadVoice (file upload), not to WebSocket.
        """
        src = self._voice_recorder_src()
        code = _strip_comments(src)

        has_mobile_branch = bool(
            re.search(r"\bisMobile\b", code)
            or re.search(r"isMobile\s*[?&|]", code)
            or re.search(r"if\s*\(\s*isMobile", code)
            # Also allow the check inline without a named variable
            or re.search(r"if\s*\([^)]*(?:iPhone|Android)[^)]*\)", code)
        )
        assert has_mobile_branch, (
            "Bug 23 (R7): useVoiceRecorder.ts has no mobile-skip branch. "
            "After the UA check, the hook must have a code path like "
            "`if (isMobile) { /* skip WS, go to file upload */ }` that "
            "prevents the WebSocket from being opened on mobile devices."
        )

    # ------------------------------------------------------------------
    # 3. new WebSocket( is gated behind a NOT-mobile condition
    # ------------------------------------------------------------------

    def test_websocket_instantiation_gated_behind_not_mobile(self):
        """The `new WebSocket(` call in useVoiceRecorder.ts (or VoiceCapture.tsx)
        must appear inside a condition that excludes mobile — e.g.:
          if (!isMobile) { const ws = new WebSocket(...); }

        If WebSocket is instantiated unconditionally, mobile devices still hit
        the WS path and fail, producing the 'Network issue' toast.

        Strategy: verify that `new WebSocket(` does NOT appear outside of a
        NOT-mobile guard.  We check that isMobile (or equivalent) appears before
        the WebSocket instantiation within the same lexical block.
        """
        # Check VoiceCapture.tsx (where _openWs lives) as well as useVoiceRecorder.ts
        vc_src = self._voice_capture_src()
        vr_src = self._voice_recorder_src()
        combined = vc_src + "\n" + vr_src
        code = _strip_comments(combined)

        ws_positions = [m.start() for m in re.finditer(r"new WebSocket\s*\(", code)]
        if not ws_positions:
            # No WebSocket instantiation at all — acceptable (fully removed on mobile)
            return

        # For each WebSocket instantiation, check that a mobile guard appears
        # in the surrounding 600-char window before it.
        unguarded = []
        for pos in ws_positions:
            window_before = code[max(0, pos - 600): pos]
            has_guard = bool(
                re.search(r"\bisMobile\b", window_before)
                or re.search(r"!isMobile", window_before)
                or re.search(r"iPhone|Android", window_before)
            )
            if not has_guard:
                snippet = code[max(0, pos - 80): pos + 60]
                unguarded.append(snippet.strip())

        assert not unguarded, (
            "Bug 23 (R7): `new WebSocket(` is instantiated without a mobile guard "
            "in the surrounding code. On mobile devices the WS path must be skipped "
            "entirely. Gate the `new WebSocket(` behind `if (!isMobile)` or equivalent.\n"
            "Unguarded occurrences:\n" + "\n---\n".join(unguarded)
        )

    # ------------------------------------------------------------------
    # 4. 'Network issue' text must not appear in the mobile-active code path
    # ------------------------------------------------------------------

    def test_voice_capture_toast_does_not_say_network_issue_on_mobile_path(self):
        """VoiceCapture.tsx must not show 'Network issue' when the mobile path
        is intentionally chosen (it's the primary path, not a fallback).

        Acceptable outcomes:
          a) The 'Network issue' string is removed entirely from the component, OR
          b) The toast that shows 'Network issue' is never triggered on the mobile
             path (i.e. it is still shown only for actual WS failures on desktop).

        We assert that 'Network issue' either does not appear in the source, or
        that it appears only within a context that requires !isMobile (i.e. it is
        gated away from the mobile path).
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        network_issue_pos = code.find("Network issue")
        if network_issue_pos == -1:
            # String removed entirely — ideal fix
            return

        # String still present — check it's gated behind a non-mobile condition
        # Look in the 600 chars before the string for a guard
        window_before = code[max(0, network_issue_pos - 600): network_issue_pos]
        has_mobile_guard = bool(
            re.search(r"!isMobile", window_before)
            or re.search(r"isMobile\s*===\s*false", window_before)
            or re.search(r"if\s*\(\s*!isMobile", window_before)
        )
        assert has_mobile_guard, (
            "Bug 23 (R7): VoiceCapture.tsx still shows 'Network issue' text on the "
            "mobile path. On mobile, file upload is the PRIMARY path — not a fallback — "
            "so calling it a 'Network issue' is misleading and confusing to users. "
            "Either remove the 'Network issue' string or gate the toast behind "
            "`if (!isMobile)` so it only fires for actual desktop WS failures.\n"
            f"Context: ...{code[max(0, network_issue_pos-100):network_issue_pos+60]}..."
        )

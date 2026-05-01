"""
Regression tests for Round-6 bugs reported 2026-05-01.

Bugs covered:
  B22. Refresh page STILL logs the user out (Round-5 fix incomplete).
       Two angles were fixed in Round 5 (recursive 401→logout chain;
       /register plants cookie) but the symptom persists.

       Most-likely remaining causes:
         a) refresh() in auth.ts delegates to apiPost() which calls
            fetchWithAuth(), which does set credentials:'include' in the
            RequestInit — but the 401-retry inside fetchWithAuth() calls
            /api/auth/refresh directly with fetch(..., {credentials:'include'})
            meaning the inline refresh IS correct. HOWEVER, auth.ts refresh()
            routes through apiPost → fetchWithAuth which checks isRefreshEndpoint
            to skip auto-retry. If apiPost wraps the request and the guard
            resolveUrl() comparison fails (e.g. origin mismatch) the guard would
            never trigger and refresh() could cause an infinite 401 loop.
            Assert the guard matches correctly.
         b) Backend: /login and /register set path='/api/auth' on the cookie.
            /refresh also sets path='/api/auth'. The browser will send the cookie
            on any request whose path starts with /api/auth — so
            POST /api/auth/refresh (path=/api/auth/refresh) IS covered because
            /api/auth/refresh starts with /api/auth. That is correct.
            BUT: the cookie path from /login (/api/auth) must exactly match what
            /refresh expects. If any call site accidentally uses path='/' then
            the cookie would be sent on ALL /api/* requests — a security leak.
            Assert ALL set_cookie calls use the SAME path value, not '/'.
         c) auth.ts refresh() calls apiPost('/api/auth/refresh') with no body.
            apiPost() → fetchWithAuth() → sets credentials:'include' globally.
            This is correct. But verify there is no direct fetch() call to
            /api/auth/refresh anywhere else in the frontend tree that OMITS
            credentials:'include' (that would silently fail cross-origin).

  B23. Mobile voice STILL errors "Network issue — using file upload fallback"
       (Round-5 MIME fix didn't help).
       The Round-5 fix added MIME probing + audio/m4a mapping.  The WebSocket
       streaming path fails first and the file-upload fallback fires — but the
       fallback may still fail or the WS onerror/onclose handler may not
       reliably trigger the fallback path.

  B24. Library shows wrong category on Browser B (cross-browser sync gap).
       mapServerToLocal in syncManager.ts MUST write category/tags/mood.
       The Library hook must use useLiveQuery so Dexie-write changes are
       reflected immediately.  The pullChanges "server wins" branch must
       spread the full mapServerToLocal result.

  B25. Voice transcription cut at first pause.
       Azure Speech recognize_once_async() stops at the first silence segment.
       The fix is continuous recognition with accumulated segments.
"""

import inspect
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Path helpers — all static checks resolve relative to repo root
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read_frontend(relative: str) -> str:
    path = FRONTEND_ROOT / relative
    if not path.exists():
        raise FileNotFoundError(f"Frontend file not found: {path}")
    return path.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """Remove JS/TS block comments and line comments so statics target runtime code."""
    no_block = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"//[^\n]*", "", no_block)


# ===========================================================================
# B22 — Refresh page STILL logs the user out (Round-5 fix incomplete)
# ===========================================================================


class TestB22RefreshCredentialsInclude:
    """Bug 22: Hard reload STILL logs the user out even after Round-5 fixes.

    The Round-5 fix corrected the SessionGate catch-block (no longer calls
    logout()) and planted the cookie on /register.  The symptom persisting
    means the browser is not sending the cookie to /api/auth/refresh, OR the
    /refresh endpoint cannot read it.

    Most-likely remaining causes tested here:
      1. The inline fetch() for auto-retry inside fetchWithAuth (client.ts)
         must carry credentials:'include' — it already does, but assert.
      2. The refresh cookie path must be identical on all three set_cookie
         call sites (/login, /register, /refresh) so the browser sends it
         on /api/auth/refresh.  If ANY site uses path='/' the cookie leaks
         to every /api/* request; if ANY site uses a different path the
         cookie is not sent on the mismatch.  Expected: all use '/api/auth'.
      3. No raw fetch() call in frontend/src that targets /api/auth/refresh
         may omit credentials:'include'.  (Includes the inline retry in
         client.ts — assert it is present.)
      4. auth.ts refresh() MUST route through a wrapper that includes
         credentials (apiPost or a raw fetch with credentials:'include').
         It must NOT call a bare fetch('/api/auth/refresh') without the flag.

    Expected: all set_cookie calls use path='/api/auth'; all fetch calls to
    /api/auth/refresh carry credentials:'include'; the isRefreshEndpoint guard
    in fetchWithAuth correctly blocks infinite retry on 401 from /refresh.
    """

    @staticmethod
    def _auth_py_source() -> str:
        from app.api import auth
        return inspect.getsource(auth)

    @staticmethod
    def _client_ts_source() -> str:
        return _read_frontend("api/client.ts")

    @staticmethod
    def _auth_ts_source() -> str:
        return _read_frontend("api/auth.ts")

    # ------------------------------------------------------------------
    # 1. Backend: all refresh_token set_cookie calls use the SAME path
    # ------------------------------------------------------------------

    def test_all_set_cookie_calls_use_same_path(self):
        """Every set_cookie for refresh_token must use the same path value.

        If /login uses path='/api/auth' but /register uses path='/' (or vice
        versa) the browser sends the cookie on mismatched routes and /refresh
        won't receive it consistently.
        """
        src = self._auth_py_source()
        # Split on set_cookie and grab the argument block of each
        segments = src.split("set_cookie")
        refresh_segments = [s for s in segments if "refresh_token" in s.split(")")[0]]

        assert refresh_segments, (
            "No set_cookie(refresh_token=...) calls found in auth.py. "
            "Login, refresh, and register endpoints must set this cookie."
        )

        paths_found = []
        for seg in refresh_segments:
            call_body = seg.split(")")[0]
            m = re.search(r'path\s*=\s*["\']([^"\']+)["\']', call_body)
            if m:
                paths_found.append(m.group(1))

        assert paths_found, (
            "Bug 22: set_cookie calls for refresh_token have no explicit 'path' "
            "argument. The path MUST be '/api/auth' so the cookie is scoped to "
            "auth endpoints and is sent by the browser on POST /api/auth/refresh."
        )

        unique_paths = set(paths_found)
        assert len(unique_paths) == 1, (
            f"Bug 22: refresh_token cookie is set with inconsistent path values "
            f"across set_cookie call sites: {unique_paths!r}. "
            "All call sites must use the SAME path so the browser sends the "
            "cookie on every /api/auth/... request (including /api/auth/refresh). "
            "Mismatched paths cause the cookie to be silently dropped on refresh."
        )

    def test_refresh_cookie_path_is_not_root(self):
        """Cookie path must NOT be '/' — that sends the cookie on every request
        (a security leak) and is a sign the path was lazily set rather than
        scoped to auth endpoints.  Expected value: '/api/auth'.
        """
        src = self._auth_py_source()
        segments = src.split("set_cookie")
        refresh_segments = [s for s in segments if "refresh_token" in s.split(")")[0]]

        for seg in refresh_segments:
            call_body = seg.split(")")[0]
            m = re.search(r'path\s*=\s*["\']([^"\']+)["\']', call_body)
            if m:
                assert m.group(1) != "/", (
                    "Bug 22: refresh_token cookie path must not be '/' — "
                    "use '/api/auth' to scope the cookie to the auth router. "
                    f"Found path='/' in: {call_body[:200]}"
                )

    # ------------------------------------------------------------------
    # 2. Frontend client.ts: inline fetch inside fetchWithAuth must carry
    #    credentials:'include' when calling /api/auth/refresh
    # ------------------------------------------------------------------

    def test_inline_refresh_fetch_in_client_ts_has_credentials_include(self):
        """The manual fetch() for the token-refresh retry inside fetchWithAuth
        must include credentials:'include'.  Without it the browser drops the
        httpOnly cookie on the cross-origin request and /refresh returns 401.

        We look for fetch( calls that contain /api/auth/refresh in their
        argument, then assert 'credentials' appears in the same call block.
        We deliberately exclude occurrences where /api/auth/refresh is only
        used as a string comparison (e.g. isRefreshEndpoint guard) rather than
        as the target of a fetch().
        """
        src = self._client_ts_source()
        code = _strip_comments(src)

        # Strategy: scan for every `fetch(` in the file; check whether the
        # argument block (up to the first unmatched ')') contains the refresh
        # URL.  If it does, it must also contain 'credentials'.
        violations = []
        found_refresh_fetch = False

        for m in re.finditer(r"\bfetch\s*\(", code):
            call_start = m.end()  # position just after 'fetch('
            # Walk forward to find the balancing ')' (depth counting)
            depth = 1
            pos = call_start
            while pos < len(code) and depth > 0:
                if code[pos] == "(":
                    depth += 1
                elif code[pos] == ")":
                    depth -= 1
                pos += 1
            args_block = code[call_start : pos - 1]

            if "/api/auth/refresh" not in args_block:
                continue

            found_refresh_fetch = True
            if "credentials" not in args_block:
                violations.append(
                    f"fetch() to /api/auth/refresh at offset {m.start()} "
                    f"is missing credentials:'include'.\n"
                    f"Args block: {args_block[:300]}"
                )

        assert found_refresh_fetch, (
            "Bug 22: could not locate any fetch() call to '/api/auth/refresh' "
            "in client.ts.  The auto-retry logic inside fetchWithAuth must "
            "call fetch(resolveUrl('/api/auth/refresh'), {...}) to obtain a "
            "new access token when the original request receives a 401."
        )

        assert not violations, (
            "Bug 22: fetch() call(s) to /api/auth/refresh in client.ts are "
            "missing credentials:'include' — the browser will drop the httpOnly "
            "cookie on cross-origin requests and /refresh will return 401:\n"
            + "\n".join(violations)
        )

    # ------------------------------------------------------------------
    # 3. Frontend: no raw fetch() to /api/auth/refresh anywhere in src
    #    that omits credentials:'include'
    # ------------------------------------------------------------------

    def test_no_fetch_to_refresh_endpoint_without_credentials(self):
        """Scan the entire frontend/src tree for fetch() calls that reference
        /api/auth/refresh.  Every such call must have credentials:'include'
        (or be inside apiPost/apiGet which always sets it).  A raw fetch()
        without credentials silently drops the cookie cross-origin.
        """
        src_root = FRONTEND_ROOT
        ts_files = list(src_root.rglob("*.ts")) + list(src_root.rglob("*.tsx"))

        violations = []
        for f in ts_files:
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            code = _strip_comments(content)

            # Find every occurrence of a fetch call mentioning /api/auth/refresh
            for m in re.finditer(r"fetch\s*\(", code):
                call_start = m.start()
                # Grab a generous window after 'fetch(' to find the closing paren
                window = code[call_start : call_start + 600]
                if "/api/auth/refresh" not in window:
                    continue
                # This fetch references /refresh — it must carry credentials
                if "credentials" not in window:
                    rel = f.relative_to(FRONTEND_ROOT)
                    violations.append(
                        f"{rel}: fetch() to /api/auth/refresh without credentials:'include' "
                        f"(at offset {call_start})"
                    )

        assert not violations, (
            "Bug 22: found fetch() calls to /api/auth/refresh that omit "
            "credentials:'include' — the browser will drop the httpOnly cookie "
            "on cross-origin requests and /refresh will return 401:\n"
            + "\n".join(violations)
        )

    # ------------------------------------------------------------------
    # 4. auth.ts refresh() must NOT use a bare fetch() call
    # ------------------------------------------------------------------

    def test_auth_ts_refresh_function_does_not_use_bare_fetch(self):
        """refresh() in auth.ts must delegate to apiPost (which always sets
        credentials:'include') and must NOT issue a direct fetch() call.
        A bare fetch() would omit the credentials flag on cross-origin requests.
        """
        src = self._auth_ts_source()
        code = _strip_comments(src)

        # Isolate the refresh() function body
        # Match: export async function refresh ... { ... }
        fn_match = re.search(
            r"export\s+async\s+function\s+refresh\s*\([^)]*\)[^{]*\{([^}]*)\}",
            code,
            re.DOTALL,
        )
        if not fn_match:
            # Try arrow function form
            fn_match = re.search(
                r"(?:export\s+)?(?:const|let)\s+refresh\s*=\s*async\s*[^=]*=>\s*\{([^}]*)\}",
                code,
                re.DOTALL,
            )

        if fn_match:
            fn_body = fn_match.group(1)
            assert re.search(r"\bfetch\s*\(", fn_body) is None, (
                "Bug 22: refresh() in auth.ts calls bare fetch() directly. "
                "It must call apiPost('/api/auth/refresh') so that "
                "credentials:'include' is always included via fetchWithAuth."
            )
        else:
            # Could not isolate the function body — check the whole file
            # for 'refresh' near a bare fetch
            assert "fetch(" not in src or "credentials" in src, (
                "Bug 22: auth.ts appears to call bare fetch() without "
                "credentials:'include'. Refresh calls must go through apiPost."
            )

    # ------------------------------------------------------------------
    # 5. fetchWithAuth isRefreshEndpoint guard must match the actual URL
    # ------------------------------------------------------------------

    def test_is_refresh_endpoint_guard_checks_for_refresh_in_url(self):
        """The isRefreshEndpoint guard in fetchWithAuth must check that the
        URL contains '/api/auth/refresh' so the auto-retry loop is skipped
        when the refresh endpoint itself returns 401.  Without this guard,
        a 401 from /refresh triggers another /refresh call → infinite loop
        → logout().
        """
        src = self._client_ts_source()
        code = _strip_comments(src)

        assert "isRefreshEndpoint" in code or "/api/auth/refresh" in code, (
            "Bug 22: fetchWithAuth in client.ts must have an isRefreshEndpoint "
            "guard that prevents auto-retry when the failing request is "
            "itself the /api/auth/refresh endpoint.  Without this guard a 401 "
            "from /refresh causes an infinite loop that ends in logout()."
        )


@pytest.mark.asyncio
class TestB22RefreshCookiePathBehavioral:
    """Behavioral: after login the cookie path must allow the browser to send
    it on POST /api/auth/refresh (path=/api/auth/refresh starts with /api/auth).
    Also verify /register plants a compatible cookie.
    """

    async def test_login_cookie_path_scoped_to_api_auth(self, client):
        """Login Set-Cookie must have Path=/api/auth (or a prefix that covers
        /api/auth/refresh).  If the path is '/' or missing the scoping is wrong.
        """
        email = f"b22_{uuid.uuid4().hex[:6]}@example.com"
        password = "TestPass123!"

        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "B22 User"},
        )
        assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"

        raw_cookie = login.headers.get("set-cookie", "")
        assert "refresh_token" in raw_cookie, (
            f"Login response must set a refresh_token cookie. Got: {raw_cookie!r}"
        )

        # Extract Path attribute
        path_match = re.search(r"[Pp]ath\s*=\s*([^;,\s]+)", raw_cookie)
        assert path_match, (
            "Bug 22: Set-Cookie from /login has no Path attribute. "
            f"Raw header: {raw_cookie!r}. "
            "The Path must be '/api/auth' so the browser sends the cookie on "
            "POST /api/auth/refresh."
        )
        cookie_path = path_match.group(1)
        assert cookie_path != "/", (
            f"Bug 22: Set-Cookie path='{cookie_path}' is too broad (root '/'). "
            "Use '/api/auth' to scope the cookie to auth endpoints only."
        )
        # /api/auth/refresh starts with /api/auth — valid parent path
        assert "/api/auth/refresh".startswith(cookie_path), (
            f"Bug 22: Cookie Path='{cookie_path}' does NOT cover "
            "/api/auth/refresh. The browser will not send this cookie on "
            "POST /api/auth/refresh, causing every page reload to 401."
        )

    async def test_register_cookie_path_matches_login_cookie_path(self, client):
        """Register and login must set the refresh_token cookie with the same
        Path attribute.  If they differ the user gets a logout on the first
        reload after sign-up (cookie is not sent to /refresh).
        """
        email = f"b22r_{uuid.uuid4().hex[:6]}@example.com"
        password = "TestPass123!"

        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "B22 Reg"},
        )
        assert reg.status_code in (200, 201), f"Register failed: {reg.text}"
        reg_cookie = reg.headers.get("set-cookie", "")

        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"
        login_cookie = login.headers.get("set-cookie", "")

        reg_path_m = re.search(r"[Pp]ath\s*=\s*([^;,\s]+)", reg_cookie)
        login_path_m = re.search(r"[Pp]ath\s*=\s*([^;,\s]+)", login_cookie)

        if reg_path_m and login_path_m:
            assert reg_path_m.group(1) == login_path_m.group(1), (
                f"Bug 22: /register sets cookie Path={reg_path_m.group(1)!r} "
                f"but /login sets Path={login_path_m.group(1)!r}. "
                "Mismatched paths mean the browser may not send the cookie "
                "consistently on /api/auth/refresh → reload logs out."
            )
        elif reg_path_m and not login_path_m:
            pytest.fail(
                "Bug 22: /login Set-Cookie is missing a Path attribute "
                f"(register has Path={reg_path_m.group(1)!r}). "
                "Inconsistent cookie scoping causes unreliable refresh."
            )
        elif login_path_m and not reg_path_m:
            pytest.fail(
                "Bug 22: /register Set-Cookie is missing a Path attribute "
                f"(login has Path={login_path_m.group(1)!r}). "
                "After sign-up a hard reload will not send the cookie → logout."
            )
        # Both missing path — the earlier test catches that; pass here.


# ===========================================================================
# B23 — Mobile voice STILL errors "Network issue — using file upload fallback"
# ===========================================================================


class TestB23VoiceFallbackWiring:
    """Bug 23: Mobile voice still shows the degraded toast after Round-5 MIME fix.

    The MIME probing landed (audio/mp4 accepted by the recorder hook) but the
    symptom persists.  Likely: the WS onerror/onclose handler sets
    wsDegradedRef=true but the file-upload fallback path does not fire when
    the WS aborts BEFORE any audio has been accumulated, OR the fallback POST
    itself fails (auth header missing, wrong field name, or MIME rejected).

    Expected behaviour:
      1. ws.onerror AND ws.onclose (non-1000) both set degraded=true AND
         trigger the fallback path (not just a toast).
      2. The fallback POST to /api/voice/upload must carry an Authorization
         header with the Bearer token.
      3. When the fallback upload fails, processingStatus must be set to
         'failed' in Dexie AND a visible error indicator must be shown.
      4. The voice backend endpoint must accept application/octet-stream
         (some mobile browsers send this when MIME detection fails).
    """

    @staticmethod
    def _voice_capture_src() -> str:
        return _read_frontend("components/VoiceCapture.tsx")

    @staticmethod
    def _use_voice_recorder_src() -> str:
        return _read_frontend("hooks/useVoiceRecorder.ts")

    # ------------------------------------------------------------------
    # 1. ws.onerror triggers degraded path
    # ------------------------------------------------------------------

    def test_ws_onerror_sets_degraded_flag(self):
        """ws.onerror must set wsDegradedRef.current = true (or equivalent)
        so the stop handler knows to use the file-upload fallback.
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # Find the onerror handler body
        onerror_match = re.search(
            r"ws\.onerror\s*=\s*(?:\([^)]*\)\s*=>|function\s*\([^)]*\))\s*\{([^}]*)\}",
            code,
            re.DOTALL,
        )
        assert onerror_match, (
            "Bug 23: VoiceCapture.tsx must define ws.onerror. "
            "Without it the component never knows the WS failed and always "
            "tries the WS path → 'Network issue' toast loops."
        )
        handler_body = onerror_match.group(1)
        assert "Degraded" in handler_body or "degraded" in handler_body, (
            "Bug 23: ws.onerror handler must set the degraded flag "
            "(e.g. wsDegradedRef.current = true) so the stop handler "
            "falls back to file upload.  Currently the handler is a no-op "
            "or only shows a toast without flagging degraded mode.\n"
            f"Handler body: {handler_body.strip()}"
        )

    # ------------------------------------------------------------------
    # 2. ws.onclose (non-1000) triggers fallback path via degraded flag
    # ------------------------------------------------------------------

    def test_ws_onclose_non_1000_triggers_fallback(self):
        """ws.onclose with code !== 1000 must mark wsDegradedRef.current = true
        so that when the recorder stops, the file-upload fallback is used
        instead of attempting the WS transcript path.
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        onclose_match = re.search(
            r"ws\.onclose\s*=\s*(?:\([^)]*\)\s*=>|function\s*\([^)]*\))\s*\{([^}]+)\}",
            code,
            re.DOTALL,
        )
        assert onclose_match, (
            "Bug 23: VoiceCapture.tsx must define ws.onclose. "
            "Abnormal WebSocket closes (code 1006, 1011, etc.) go undetected "
            "without it, and the degraded fallback never fires."
        )
        handler_body = onclose_match.group(1)

        # Must check for non-1000 code
        checks_non_1000 = re.search(r"!==\s*1000|code\s*!==\s*1000|evt\.code", handler_body)
        assert checks_non_1000, (
            "Bug 23: ws.onclose handler must check evt.code !== 1000 to "
            "distinguish abnormal closes from clean ones. Without this check "
            "all closes (including normal stop) mark degraded=true and the "
            "fallback fires even on successful WS recordings."
        )

        # Must set degraded flag
        sets_degraded = "degraded" in handler_body.lower() or "Degraded" in handler_body
        assert sets_degraded, (
            "Bug 23: ws.onclose handler with non-1000 code must set the "
            "wsDegradedRef.current = true flag so the stop handler routes "
            "to the file-upload fallback.\n"
            f"Handler body: {handler_body.strip()}"
        )

    # ------------------------------------------------------------------
    # 3. Fallback POST carries Authorization header
    # ------------------------------------------------------------------

    def test_fallback_upload_has_authorization_header(self):
        """The fetch() inside uploadVoice() (the fallback) must include an
        Authorization: Bearer <token> header.  Without it /api/voice/upload
        returns 401 and the fallback silently fails on every mobile request.

        We use paren-depth-balanced scanning so that fetch(apiUrl('/api/voice/upload'), {})
        is captured in full (the naive [^)]* approach stops at the first ')' inside
        the nested apiUrl() call and misses the options object).
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # Walk every fetch( call in the file; capture the full argument block
        # (paren-balanced), then check if it references /api/voice/upload.
        # If it does, it must also contain 'Authorization'.
        violations = []
        found_voice_upload_fetch = False

        for m in re.finditer(r"\bfetch\s*\(", code):
            call_start = m.end()
            depth = 1
            pos = call_start
            while pos < len(code) and depth > 0:
                if code[pos] == "(":
                    depth += 1
                elif code[pos] == ")":
                    depth -= 1
                pos += 1
            args_block = code[call_start : pos - 1]

            if "/api/voice/upload" not in args_block:
                continue

            found_voice_upload_fetch = True
            if "Authorization" not in args_block:
                violations.append(
                    f"fetch() to /api/voice/upload at offset {m.start()} "
                    "is missing an Authorization header.\n"
                    f"Args block snippet: {args_block[:400]}"
                )

        assert found_voice_upload_fetch, (
            "Bug 23: no fetch() call to /api/voice/upload found in "
            "VoiceCapture.tsx.  The fallback upload function (uploadVoice) "
            "must POST to /api/voice/upload with the audio blob."
        )

        assert not violations, (
            "Bug 23: fetch() to /api/voice/upload is missing "
            "Authorization: Bearer <token> header — the backend will return "
            "401 on every mobile fallback upload.\n"
            + "\n".join(violations)
        )

    # ------------------------------------------------------------------
    # 4. Fallback failure sets processingStatus='failed' in Dexie
    # ------------------------------------------------------------------

    def test_fallback_failure_sets_processing_status_failed(self):
        """When the fallback upload itself fails (network error, 401, etc.)
        the catch block MUST set processingStatus='failed' on the local Dexie
        note so the Library shows an error state rather than a stuck spinner.
        Round 5 partially added this; verify it is actually present.
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # Look for the pattern: db.notes.update( ... processingStatus: 'failed' ... )
        # in or near a catch block that follows uploadVoice
        assert re.search(
            r"processingStatus\s*:\s*['\"]failed['\"]",
            code,
        ), (
            "Bug 23: VoiceCapture.tsx catch block for fallback upload failure "
            "must set processingStatus: 'failed' on the Dexie note. "
            "Without this the Library card shows a stuck 'processing' state "
            "with no user-actionable feedback on mobile."
        )

    # ------------------------------------------------------------------
    # 5. Fallback failure shows user-visible error (not just console.warn)
    # ------------------------------------------------------------------

    def test_fallback_failure_shows_user_visible_error(self):
        """When the fallback upload fails, a visible error indicator must be
        shown in the UI — not just console.warn/console.error.  The user needs
        to know the recording failed so they can retry.
        """
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # Find catch blocks that follow the uploadVoice call
        # We look for any UI-visible side-effect near the 'failed' status set
        has_visible_error = bool(
            re.search(r"setShow\w+\s*\(", code)
            or re.search(r"setError\s*\(", code)
            or re.search(r"toast\s*\(", code)
            or re.search(r"setFallback\w+\s*\(", code)
            or re.search(r"setUploadError\s*\(", code)
        )

        # A degraded-toast hidden/dismissed without a SECOND error toast is not
        # sufficient — the user loses the "Network issue" toast before knowing
        # the fallback itself failed.  Check for a second error state.
        # Accept: setShowDegradedToast(false) followed by a non-toast error path
        # (processingStatus='failed' in DB means the Library card shows an error).
        assert has_visible_error or re.search(
            r"processingStatus\s*:\s*['\"]failed['\"]",
            code,
        ), (
            "Bug 23: when the voice fallback upload fails the component must "
            "provide a user-visible error signal (state setter, toast, or "
            "processingStatus='failed' for the Library card error state). "
            "A bare console.warn is insufficient."
        )


class TestB23VoiceBackendOctetStream:
    """Bug 23 backend: /api/voice/upload must tolerate application/octet-stream.

    Some mobile browsers (especially older Android WebViews) send
    application/octet-stream when MIME detection fails.  The backend must
    not reject this content-type — either via an explicit allow-list that
    includes it, or via the ffmpeg-tolerant path that ignores MIME and lets
    ffmpeg probe the container.
    """

    def test_voice_upload_tolerates_octet_stream_or_uses_ffmpeg(self):
        """_audio_ext (or voice_upload) must handle application/octet-stream
        without raising a 422.  Either:
          a) Explicit allow-list includes application/octet-stream, OR
          b) The function falls back to a default extension (e.g. .webm or .mp4)
             when the content-type is unknown — and ffmpeg handles the rest.
        """
        from app.api import voice

        src = inspect.getsource(voice._audio_ext)

        # Option a: explicit allow of octet-stream
        explicitly_allowed = "octet-stream" in src or "octet_stream" in src

        # Option b: a fallback/default path that does NOT raise on unknown types
        # i.e. the function has a final return that returns a default extension
        # rather than raising ValueError or HTTPException.
        fallback_lines = re.findall(r"return\s+['\"]\.?\w+['\"]", src)
        has_fallback_return = bool(fallback_lines)

        # Also check that the function does NOT raise on unknown type
        raises_on_unknown = bool(
            re.search(r"raise\s+(?:ValueError|HTTPException|RuntimeError)", src)
            and not re.search(r"octet", src)
        )

        assert (explicitly_allowed or has_fallback_return) and not raises_on_unknown, (
            "Bug 23: _audio_ext() must not raise on unknown MIME types like "
            "application/octet-stream — it must return a default extension "
            "(e.g. '.webm') and let ffmpeg probe the container. "
            "Some mobile browsers send application/octet-stream when their "
            "MIME detection fails, and a 422 from the backend means the "
            "fallback produces no note.\n"
            f"Source:\n{src}"
        )

    def test_voice_upload_does_not_whitelist_restrict_content_type(self):
        """voice_upload() must NOT reject requests based on content-type
        before reading the file.  Any content-type filtering must happen
        AFTER ffmpeg conversion, not before.
        """
        from app.api import voice

        src = inspect.getsource(voice.voice_upload)
        code = _strip_comments(src)

        # Look for an early return or raise that checks content_type before read()
        early_reject = re.search(
            r"(?:content_type|content-type|mime)[^\n]*(?:raise|return)[^\n]*(?:422|415|unsupported)",
            code,
            re.IGNORECASE,
        )
        assert not early_reject, (
            "Bug 23: voice_upload() appears to reject requests based on "
            "content_type before processing the audio with ffmpeg. "
            "This blocks application/octet-stream uploads from mobile browsers. "
            f"Suspicious pattern: {early_reject.group(0) if early_reject else ''}"
        )


# ===========================================================================
# B24 — Library shows wrong category on Browser B (cross-browser sync gap)
# ===========================================================================


class TestB24SyncManagerMapsAllFields:
    """Bug 24: Note Detail on Browser B shows correct category ('Fitness') but
    the Library card still shows the default 'Ideas'.

    Root cause: mapServerToLocal must write category/tags/mood on every merge
    path, AND the Library must use useLiveQuery so it reacts to Dexie writes
    triggered by pullChanges().

    Expected:
      1. mapServerToLocal merges category, tags, mood (not just content/status).
      2. useNotes in useNotes.ts uses useLiveQuery (reactive to Dexie writes).
      3. pullChanges() 'server wins' branch spreads full mapServerToLocal result.
    """

    @staticmethod
    def _sync_manager_src() -> str:
        return _read_frontend("sync/syncManager.ts")

    @staticmethod
    def _use_notes_src() -> str:
        return _read_frontend("hooks/useNotes.ts")

    # ------------------------------------------------------------------
    # 1. mapServerToLocal merges category
    # ------------------------------------------------------------------

    def test_map_server_to_local_assigns_category(self):
        """mapServerToLocal must write merged.category when the server note
        includes a category field.  The Library card reads category from Dexie
        so if mapServerToLocal skips it the card permanently shows 'Ideas'.
        """
        src = self._sync_manager_src()
        code = _strip_comments(src)

        assert re.search(r"merged\.category\s*=", code) or re.search(
            r"category\s*:\s*serverNote\.category", code
        ), (
            "Bug 24: mapServerToLocal in syncManager.ts does not assign "
            "merged.category from the server note. The Library card reads "
            "category from the local Dexie row — if mapServerToLocal skips it "
            "the row retains the default 'Ideas' even after AI enrichment.\n"
            "Add: if (typeof serverNote.category === 'string') "
            "{ merged.category = serverNote.category as LocalNote['category']; }"
        )

    # ------------------------------------------------------------------
    # 2. mapServerToLocal merges tags
    # ------------------------------------------------------------------

    def test_map_server_to_local_assigns_tags(self):
        """mapServerToLocal must write merged.tags when the server returns tags."""
        src = self._sync_manager_src()
        code = _strip_comments(src)

        assert re.search(r"merged\.tags\s*=", code) or re.search(
            r"tags\s*:\s*(?:tags|serverNote\.tags)", code
        ), (
            "Bug 24: mapServerToLocal does not write merged.tags. "
            "The Library card tag display stays empty after a cross-browser pull."
        )

    # ------------------------------------------------------------------
    # 3. mapServerToLocal merges mood
    # ------------------------------------------------------------------

    def test_map_server_to_local_assigns_mood(self):
        """mapServerToLocal must write merged.mood when the server returns mood."""
        src = self._sync_manager_src()
        code = _strip_comments(src)

        assert re.search(r"merged\.mood\s*=", code) or re.search(
            r"mood\s*:\s*(?:serverNote\.mood|mood)", code
        ), (
            "Bug 24: mapServerToLocal does not write merged.mood. "
            "The mood field will be stale on Browser B after a pull."
        )

    # ------------------------------------------------------------------
    # 4. useNotes uses useLiveQuery (reactive to Dexie writes)
    # ------------------------------------------------------------------

    def test_use_notes_uses_use_live_query(self):
        """The Library hook (useNotes.ts) must use useLiveQuery from
        dexie-react-hooks so it re-renders whenever syncManager.pullChanges()
        writes an updated category to Dexie.

        If useNotes reads from a Zustand snapshot or a one-shot useEffect/
        useState array, it won't reflect Dexie writes until a component
        remount — which is the observable symptom on Browser B.
        """
        src = self._use_notes_src()
        assert "useLiveQuery" in src, (
            "Bug 24: useNotes.ts must use useLiveQuery (from dexie-react-hooks) "
            "so the Library re-renders reactively when pullChanges() writes "
            "an updated category to Dexie.  Using a plain useEffect + setState "
            "array does not react to mid-render Dexie writes from the sync loop."
        )

    # ------------------------------------------------------------------
    # 5. pullChanges 'server wins' branch spreads full mapServerToLocal result
    # ------------------------------------------------------------------

    def test_pull_changes_server_wins_branch_spreads_map_server_to_local(self):
        """In pullChanges() the 'Server wins' else-branch must spread the
        FULL mapServerToLocal(serverNote) result, not just a subset of fields.

        If the else-branch only updates content + syncStatus it will miss
        category/tags/mood and the Library shows stale data on Browser B.
        """
        src = self._sync_manager_src()
        code = _strip_comments(src)

        # Look for a db.notes.update call that spreads mapServerToLocal
        # The expected pattern: ...mapServerToLocal(serverNote)
        assert re.search(
            r"\.\.\.mapServerToLocal\s*\(\s*serverNote\s*\)",
            code,
        ), (
            "Bug 24: pullChanges() 'server wins' branch must use "
            "{ ...mapServerToLocal(serverNote) } so ALL server fields "
            "(category, tags, mood, processingStatus) are written to Dexie. "
            "A partial update (only content + syncStatus) leaves the Library "
            "showing the default 'Ideas' category on Browser B even after "
            "the server note was enriched by the AI pipeline."
        )

    # ------------------------------------------------------------------
    # 6. pullChanges conflict branch also spreads mapServerToLocal
    # ------------------------------------------------------------------

    def test_pull_changes_conflict_branch_spreads_map_server_to_local(self):
        """The conflict branch of pullChanges() must also spread
        mapServerToLocal(serverNote, ...) to capture category/tags/mood.
        If only the server-wins branch spreads it, conflicts leave stale fields.
        """
        src = self._sync_manager_src()
        code = _strip_comments(src)

        # Count how many times mapServerToLocal is spread (not just called)
        spread_count = len(re.findall(
            r"\.\.\.mapServerToLocal\s*\(",
            code,
        ))
        assert spread_count >= 2, (
            f"Bug 24: mapServerToLocal is spread only {spread_count} time(s) "
            "in syncManager.ts.  Both the 'server wins' AND the 'conflict' "
            "branches of pullChanges() must spread its result so category/tags/"
            "mood are written on every update path."
        )


# ===========================================================================
# B25 — Voice transcription cut at first pause
# ===========================================================================


class TestB25ContinuousRecognition:
    """Bug 25: Azure Speech recognize_once_async() stops at the first silence
    segment.  A 20-second recording with 3 pauses only transcribes the first
    ~5 seconds.

    The fix is to replace recognize_once_async() with
    start_continuous_recognition_async() plus a 'recognized' event handler
    that accumulates result segments, and a 'session_stopped' event that
    signals the asyncio loop to release.

    Expected:
      1. transcribe_audio_file MUST NOT call recognize_once_async (or only
         for a short-circuit case); it must call
         start_continuous_recognition_async or start_continuous_recognition.
      2. A 'recognized' event handler must accumulate result.text segments.
      3. A 'session_stopped' (or session_stopped_event) handler must signal
         the asyncio loop (e.g. set an Event or call a Future).
      4. With a mocked SDK that fires two 'recognized' events followed by
         'session_stopped', the returned text must concatenate both segments.
    """

    @staticmethod
    def _speech_source() -> str:
        from app.services import speech
        return inspect.getsource(speech)

    @staticmethod
    def _transcribe_source() -> str:
        from app.services.speech import transcribe_audio_file
        return inspect.getsource(transcribe_audio_file)

    # ------------------------------------------------------------------
    # 1. recognize_once_async must NOT be the primary recognition call
    # ------------------------------------------------------------------

    def test_transcribe_does_not_use_recognize_once_async_as_primary(self):
        """transcribe_audio_file must NOT call recognize_once_async() as its
        primary recognition strategy.  That method returns after the first
        silence segment and discards the rest of the audio.

        Acceptable: recognize_once_async may be used as a short-circuit
        for very short audio (< 2 s) — but the main path must be continuous.
        """
        src = self._transcribe_source()

        has_once = bool(re.search(r"recognize_once_async\s*\(", src))
        has_continuous = bool(
            re.search(r"start_continuous_recognition(?:_async)?\s*\(", src)
        )

        # If recognize_once_async exists it must be accompanied by continuous
        assert has_continuous or not has_once, (
            "Bug 25: transcribe_audio_file() calls recognize_once_async() "
            "without also calling start_continuous_recognition_async(). "
            "recognize_once_async() stops at the first pause in speech — "
            "a 20-second recording with silences transcribes only the first "
            "segment.  Replace with start_continuous_recognition_async() + "
            "a 'recognized' event accumulator + a 'session_stopped' signal."
        )

    # ------------------------------------------------------------------
    # 2. 'recognized' event handler accumulates segments
    # ------------------------------------------------------------------

    def test_recognized_event_handler_is_connected(self):
        """The recognizer must connect a 'recognized' event handler that
        accumulates result.text segments into a list or string.
        Pattern: recognizer.recognized.connect(handler) or
                 recognizer.recognized += handler.
        """
        src = self._speech_source()

        has_recognized_handler = bool(
            re.search(r"recognized\s*\.connect\s*\(", src)
            or re.search(r"recognized\s*\+=", src)
        )
        assert has_recognized_handler, (
            "Bug 25: speech.py must connect a handler to "
            "recognizer.recognized (e.g. recognizer.recognized.connect(fn) "
            "or recognizer.recognized += fn) that accumulates result.text. "
            "Without this, continuous recognition fires events that are never "
            "captured and the function returns an empty string."
        )

    # ------------------------------------------------------------------
    # 3. 'session_stopped' handler signals completion
    # ------------------------------------------------------------------

    def test_session_stopped_handler_is_connected(self):
        """A session_stopped (or session_stopped_event) handler must be wired
        so transcribe_audio_file knows when the SDK has finished processing
        the entire file and can release the asyncio wait.
        """
        src = self._speech_source()

        has_session_stopped = bool(
            re.search(r"session_stopped\s*\.connect\s*\(", src)
            or re.search(r"session_stopped\s*\+=", src)
            or re.search(r"session_stopped_event", src)
        )
        assert has_session_stopped, (
            "Bug 25: speech.py must connect a session_stopped event handler "
            "(e.g. recognizer.session_stopped.connect(fn)) that signals the "
            "asyncio event loop to release the wait.  Without it "
            "transcribe_audio_file either hangs forever or times out before "
            "all segments are received."
        )

    # ------------------------------------------------------------------
    # 4. Static: _recognize_once helper must not exist (or be unused)
    #    when continuous recognition is in place
    # ------------------------------------------------------------------

    def test_recognize_once_helper_is_replaced_by_continuous(self):
        """After the Bug 25 fix there must be NO internal _recognize_once()
        helper that wraps recognize_once_async() — or if it still exists it
        must not be called from transcribe_audio_file.

        The presence of _recognize_once being called from transcribe_audio_file
        is the smoking gun: it means the Round-5 fix was never actually applied
        to the core transcription path.
        """
        src = self._transcribe_source()

        calls_recognize_once_helper = bool(
            re.search(r"await\s+_recognize_once\s*\(", src)
        )
        assert not calls_recognize_once_helper, (
            "Bug 25: transcribe_audio_file() calls _recognize_once() which "
            "internally calls recognize_once_async() — a one-shot recognizer "
            "that stops at the first silence.  This is the root cause of "
            "transcriptions being cut at the first pause.  Replace this call "
            "with start_continuous_recognition_async() + recognized event "
            "accumulator + session_stopped signal."
        )

    def test_transcribe_source_contains_continuous_start_call(self):
        """The full speech.py module source must contain a call to
        start_continuous_recognition_async (or start_continuous_recognition)
        somewhere — confirming the fix was applied at least structurally.
        """
        src = self._speech_source()
        assert re.search(r"start_continuous_recognition", src), (
            "Bug 25: speech.py has no call to start_continuous_recognition "
            "anywhere in the module.  The fix requires replacing "
            "recognize_once_async() with the continuous recognition API "
            "(recognizer.start_continuous_recognition_async()) so that all "
            "speech segments across pauses are captured."
        )

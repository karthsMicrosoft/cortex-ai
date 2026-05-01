"""
Regression tests for Round-5 bugs reported 2026-05-01.

Bugs covered:
  B18. Refresh page logs out (regression) — refresh-token cookie attributes
       (SameSite=None + Secure + httponly) must be present on all three auth
       set-cookie call sites (/login, /refresh, /register). SessionGate must
       NOT call logout() on refresh failure — it must leave the user
       unauthenticated and let AuthGate redirect.

  B19. Delete not syncing across browsers — hard-deletes produce no tombstone,
       so /api/sync/pull always returns deletions=[]. Requires a NoteDeletion
       model + note_deletions table + migration, and /api/sync/pull must query
       it and populate the deletions field.

  B20. Mobile voice "Network issue — using file upload fallback" then nothing
       — fallback posts to the wrong endpoint OR uses wrong field name OR the
       backend voice endpoint rejects mobile MIME types (audio/mp4, audio/aac,
       audio/m4a). Frontend fallback must also propagate a user-visible error
       if the fallback itself fails, not just console.error.

  B21. Desktop voice creates duplicate note (one good, one failed) — the local
       Dexie note created immediately on stop must be marked syncStatus='synced'
       and assigned a serverId after the upload succeeds, so pushChanges() won't
       create a second server row. Alternatively, voice recordings never create
       a pending local note. Backend must also dedup on client_id.
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
# B18 — Refresh page logs out (regression)
# ===========================================================================


class TestB18RefreshTokenCookieAttributes:
    """Bug 18: Hard reload logs the user out.

    Root cause: refresh-token cookie regressed away from SameSite=None+Secure
    on one of the three auth set-cookie call sites (login / refresh / register),
    OR the SessionGate catch block calls logout() and clears the auth store
    aggressively instead of leaving the user unauthenticated for AuthGate to
    handle.

    Expected: every set_cookie(key='refresh_token', ...) call in auth.py must
    have samesite='none', secure=True, httponly=True. SessionGate catch must
    NOT call logout().
    """

    @staticmethod
    def _auth_source() -> str:
        from app.api import auth
        return inspect.getsource(auth)

    def test_login_set_cookie_has_samesite_none(self):
        src = self._auth_source()
        # Find all set_cookie blocks — we need every one containing refresh_token
        # to have samesite="none". The simplest stable check: count occurrences.
        blocks = re.findall(
            r'set_cookie\s*\([^)]*key\s*=\s*["\']refresh_token["\'][^)]*\)',
            src,
            re.DOTALL,
        )
        # If there are no explicit blocks the keyword arg pattern may span more than
        # one line — fall back to a global scan.
        if not blocks:
            # Check the full source: every samesite arg near a refresh_token cookie
            login_block = re.search(
                r'samesite\s*=\s*["\']none["\']', src, re.IGNORECASE
            )
            assert login_block is not None, (
                "auth.py must set samesite='none' on the refresh_token cookie. "
                "Without SameSite=None the cross-origin SWA→backend cookie is "
                "silently dropped by the browser and /refresh always returns 401."
            )
            return
        # All found blocks must contain samesite=none
        for block in blocks:
            assert re.search(r'samesite\s*=\s*["\']none["\']', block, re.IGNORECASE), (
                f"set_cookie block for refresh_token is missing samesite='none':\n{block}"
            )

    def test_all_refresh_token_set_cookie_calls_have_secure_true(self):
        src = self._auth_source()
        # Count set_cookie calls that mention refresh_token
        cookie_sites = list(re.finditer(
            r'set_cookie\s*\(', src
        ))
        # For each set_cookie call site find the nearest "secure" setting
        # A robust check: anywhere in the source that sets the refresh cookie,
        # secure=True must appear within the same logical block.
        # We use a simple heuristic: split by "set_cookie" and check each segment.
        segments = src.split("set_cookie")
        refresh_segments = [s for s in segments if "refresh_token" in s.split(")")[0]]
        assert refresh_segments, (
            "Could not find any set_cookie(... refresh_token ...) call in auth.py. "
            "The login / refresh endpoints must set this cookie."
        )
        for seg in refresh_segments:
            # grab up to the first closing paren
            call_body = seg.split(")")[0]
            assert "secure=True" in call_body, (
                "Every set_cookie for 'refresh_token' must pass secure=True. "
                f"Segment missing it:\n{call_body[:300]}"
            )

    def test_all_refresh_token_set_cookie_calls_have_httponly_true(self):
        src = self._auth_source()
        segments = src.split("set_cookie")
        refresh_segments = [s for s in segments if "refresh_token" in s.split(")")[0]]
        assert refresh_segments
        for seg in refresh_segments:
            call_body = seg.split(")")[0]
            assert "httponly=True" in call_body, (
                "Every set_cookie for 'refresh_token' must pass httponly=True. "
                f"Segment missing it:\n{call_body[:300]}"
            )

    def test_register_endpoint_sets_refresh_cookie(self):
        """Register must also set the refresh cookie so the user is
        immediately session-persistent after sign-up (no second login needed)."""
        src = self._auth_source()
        # Find the register function source
        register_src = inspect.getsource(
            __import__("app.api.auth", fromlist=["register"]).register
        )
        assert "set_cookie" in register_src and "refresh_token" in register_src, (
            "Bug 18: /api/auth/register must call response.set_cookie for "
            "refresh_token — without it, a hard reload after sign-up logs the "
            "user out immediately (cookie is never planted)."
        )

    def test_session_gate_catch_does_not_call_logout(self):
        """SessionGate must NOT call logout() in the catch block — it should
        just leave the user unauthenticated and let AuthGate redirect to /login.
        Calling logout() would additionally clear any auth state set by a
        concurrent tab, or wipe the Dexie DB unexpectedly."""
        src = _read_frontend("components/SessionGate.tsx")
        code = _strip_comments(src)

        # Identify the catch block inside the useEffect that calls refresh()
        # We look for the pattern: catch { ... logout() ... }
        # The fix: catch must NOT contain a logout() call.
        catch_blocks = re.findall(r'catch\s*(?:\([^)]*\))?\s*\{([^}]*)\}', code)
        for block in catch_blocks:
            assert "logout" not in block, (
                "SessionGate catch block must NOT call logout() — "
                "that aggressively wipes auth state for every network hiccup. "
                "Instead, call setRestoring(false) and let AuthGate redirect.\n"
                f"Found logout() in catch block: {block[:200]}"
            )


@pytest.mark.asyncio
class TestB18RefreshBehavioral:
    """Behavioral check: a client with only the refresh cookie (no Authorization
    header) must be able to call POST /api/auth/refresh and get a new access_token."""

    async def test_refresh_with_cookie_only_returns_access_token(self, client):
        """Register → login (plants cookie) → call /refresh with cookie only."""
        email = f"b18_{uuid.uuid4().hex[:6]}@example.com"
        password = "TestPass123!"

        # Register
        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "B18 User"},
        )
        assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

        # Login — sets the refresh_token cookie
        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"

        # Extract the refresh cookie from Set-Cookie header
        raw_cookie = login.headers.get("set-cookie", "")
        assert "refresh_token" in raw_cookie, (
            "Login response must set a 'refresh_token' cookie. "
            f"Got Set-Cookie: {raw_cookie!r}"
        )
        # Pull the token value (format: refresh_token=<value>; ...)
        match = re.search(r"refresh_token=([^;]+)", raw_cookie)
        assert match, f"Could not parse refresh_token value from: {raw_cookie}"
        cookie_value = match.group(1)

        # Call /refresh carrying ONLY the cookie (no Authorization header)
        refresh_resp = await client.post(
            "/api/auth/refresh",
            headers={"Cookie": f"refresh_token={cookie_value}"},
        )
        assert refresh_resp.status_code == 200, (
            f"POST /api/auth/refresh with cookie-only returned {refresh_resp.status_code}: "
            f"{refresh_resp.text}\n"
            "Bug 18: the refresh endpoint must honour the httpOnly cookie so a "
            "hard reload can silently restore the session."
        )
        data = refresh_resp.json()
        assert "access_token" in data, (
            f"Refresh response body missing 'access_token': {data}"
        )


# ===========================================================================
# B19 — Delete not syncing across browsers
# ===========================================================================


class TestB19DeletionTombstoneModel:
    """Bug 19: deletes are hard-deleted with no tombstone, so /api/sync/pull
    always returns deletions=[] and Browser B never learns about the delete.

    Expected: a NoteDeletion model must exist in app.models, the note_deletions
    table must have at least id / user_id / deleted_at columns, and there must
    be an Alembic migration creating that table. /api/sync/pull must query
    NoteDeletion.deleted_at >= since and return the deleted IDs.
    """

    def test_note_deletion_model_is_importable(self):
        try:
            from app.models.note_deletion import NoteDeletion  # noqa: F401
        except ImportError:
            try:
                from app.models import NoteDeletion  # noqa: F401
            except ImportError:
                pytest.fail(
                    "Bug 19: NoteDeletion model is not importable from "
                    "app.models.note_deletion or app.models. "
                    "Create it so the sync layer can record tombstones."
                )

    def test_note_deletion_model_has_required_columns(self):
        try:
            from app.models.note_deletion import NoteDeletion
        except ImportError:
            try:
                from app.models import NoteDeletion
            except ImportError:
                pytest.fail("NoteDeletion model not found — see previous test.")
                return

        src = inspect.getsource(NoteDeletion)
        assert "user_id" in src, "NoteDeletion must have a user_id column"
        assert "deleted_at" in src, "NoteDeletion must have a deleted_at column"
        # The model must identify WHICH note was deleted.
        # Acceptable designs:
        #   (a) a separate note_id / note_uuid column (FK to notes.id), OR
        #   (b) id IS the mirrored note.id (primary key = deleted note UUID),
        #       in which case the docstring / comment should say so.
        has_explicit_note_id_col = bool(re.search(r"\bnote_id\b|\bnote_uuid\b", src))
        id_mirrors_note_id = (
            "id" in src
            and (
                "Mirrors the original note" in src
                or "mirrors" in src.lower()
                or "original note" in src.lower()
                or "note.id" in src
            )
        )
        assert has_explicit_note_id_col or id_mirrors_note_id, (
            "NoteDeletion must identify which note was deleted. Either add a "
            "note_id column (FK to notes.id) OR use id = original_note.id as "
            "the primary key with a clear docstring that it mirrors notes.id."
        )

    def test_alembic_migration_creates_note_deletions_table(self):
        versions_dir = REPO_ROOT / "backend" / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*.py"))
        assert migration_files, "No alembic migration files found"

        found = False
        for mf in migration_files:
            content = mf.read_text(encoding="utf-8")
            if "note_deletions" in content:
                found = True
                # Verify it creates the table with minimum columns
                assert "user_id" in content, (
                    f"Migration {mf.name} mentions note_deletions but "
                    "doesn't declare a user_id column."
                )
                assert "deleted_at" in content, (
                    f"Migration {mf.name} mentions note_deletions but "
                    "doesn't declare a deleted_at column."
                )
                break

        assert found, (
            "Bug 19: No alembic migration file contains 'note_deletions'. "
            "Create a new migration (e.g. 006_add_note_deletions.py) that "
            "creates the note_deletions table with id, user_id, note_id, "
            "deleted_at columns."
        )

    def test_sync_pull_queries_note_deletions(self):
        from app.api import sync

        src = inspect.getsource(sync.sync_pull)
        assert "NoteDeletion" in src or "note_deletion" in src or "deletions" in src, (
            "sync_pull must reference NoteDeletion (or a note_deletion query) "
            "to populate the deletions field."
        )
        # The current implementation always returns deletions=[] — that's the bug.
        # Check that deletions=[] is NOT the only return site, or that it queries
        # something meaningful.
        static_empty = re.findall(r'deletions\s*=\s*\[\s*\]', src)
        queries_model = "NoteDeletion" in src or "note_deletions" in src
        assert queries_model or not static_empty, (
            "Bug 19: /api/sync/pull unconditionally returns deletions=[]. "
            "It must query NoteDeletion.deleted_at >= since_dt and return "
            "the matching note IDs in the deletions list."
        )


@pytest.mark.asyncio
class TestB19DeletionBehavioral:
    """Behavioral: delete a note then call /sync/pull — deletions must not be empty."""

    async def test_deleted_note_id_appears_in_sync_pull_deletions(
        self, client, auth_headers
    ):
        from datetime import datetime, timezone
        from urllib.parse import quote

        # Create a note
        create_resp = await client.post(
            "/api/notes",
            json={"content": "B19 deletion test note", "source_type": "text"},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201, f"Note create failed: {create_resp.text}"
        note_id = create_resp.json()["id"]

        # Record a timestamp just before delete — use UTC Z suffix to avoid the
        # '+00:00' form which httpx/starlette may not percent-encode, causing
        # the '+' to be parsed as a space and the timestamp rejected as invalid.
        before_delete = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

        # Delete the note
        del_resp = await client.delete(f"/api/notes/{note_id}", headers=auth_headers)
        assert del_resp.status_code in (200, 204), f"Delete failed: {del_resp.text}"

        # Pull since just-before-delete — the deleted ID must appear in deletions
        pull_resp = await client.get(
            "/api/sync/pull",
            params={"since": before_delete},
            headers=auth_headers,
        )
        assert pull_resp.status_code == 200, f"Sync pull failed: {pull_resp.text}"
        body = pull_resp.json()
        assert "deletions" in body, f"Sync pull response missing 'deletions' field: {body}"
        deletions = body["deletions"]
        assert str(note_id) in [str(d) for d in deletions], (
            f"Bug 19: deleted note {note_id} did not appear in sync/pull deletions. "
            f"Got deletions={deletions!r}. "
            "The backend must record a tombstone on DELETE and return it in pull."
        )


# ===========================================================================
# B20 — Mobile voice fallback does nothing
# ===========================================================================


class TestB20VoiceFallbackFrontendStatic:
    """Bug 20: WebSocket fails on mobile ("Network issue — using file upload
    fallback") and then the fallback creates no note.

    Expected: the fallback in VoiceCapture.tsx (or useVoiceRecorder.ts) must
    POST to /api/voice/upload (not /api/upload/audio), use field name 'file',
    AND propagate a visible UI error if the fallback itself fails.
    """

    @staticmethod
    def _voice_capture_src() -> str:
        return _read_frontend("components/VoiceCapture.tsx")

    def test_fallback_posts_to_voice_upload_not_audio_upload(self):
        src = self._voice_capture_src()
        # Check that the fallback path uses /api/voice/upload
        assert "/api/voice/upload" in src, (
            "Bug 20: VoiceCapture.tsx fallback must POST to /api/voice/upload "
            "(the STT + note-creation endpoint), NOT /api/upload/audio. "
            "The fallback currently creates no note because it posts to the wrong URL."
        )

    def test_fallback_does_not_post_to_wrong_endpoint(self):
        src = self._voice_capture_src()
        # /api/upload/audio is the wrong endpoint (it only stores the blob, no note)
        assert "/api/upload/audio" not in src, (
            "Bug 20: VoiceCapture.tsx must NOT reference /api/upload/audio — "
            "that endpoint does not perform STT or create a Note. "
            "Use /api/voice/upload instead."
        )

    def test_fallback_formdata_uses_field_name_file(self):
        src = self._voice_capture_src()
        code = _strip_comments(src)
        # The fallback FormData must append with field name 'file' (backend expects it)
        assert "formData.append('file'" in code or 'formData.append("file"' in code, (
            "Bug 20: the voice fallback FormData must use field name 'file' "
            "(matching the backend UploadFile parameter). "
            "Using 'audio' triggers 422 'Field required: body.file'."
        )

    def test_fallback_has_user_visible_error_state_not_just_console_error(self):
        src = self._voice_capture_src()
        code = _strip_comments(src)
        # The fallback catch must do more than console.error — it must update UI state
        # Look for a state setter or toast trigger in the catch after uploadVoice
        # Strategy: find the catch block that follows uploadVoice / uploadBlob
        # and assert something other than only console.error is called.

        # We look for at least one of: setState, setShow*, toast, setError, throw
        # near the fallback error path. A bare `catch { }` or `catch { console.error }`
        # is not sufficient.
        fallback_error_patterns = [
            r'setShow\w+\s*\(',      # e.g. setShowError(true)
            r'setError\s*\(',        # e.g. setError('...')
            r'toast\s*\(',           # toast library call
            r'setState\s*\(',        # generic setState
        ]
        found_visible_error = any(
            re.search(pat, code) for pat in fallback_error_patterns
        )
        # Also acceptable: the outer catch leaves syncStatus='pending' (syncManager retries)
        # but there must still be a visible indicator — check for a terminal error render
        has_terminal_error_render = re.search(
            r'(fallback.*failed|upload.*failed|error.*state|setFallbackFailed|setUploadError)',
            code,
            re.IGNORECASE,
        )
        assert found_visible_error or has_terminal_error_render, (
            "Bug 20: when the voice fallback upload itself fails, the component "
            "must propagate a user-visible error state (e.g. setShowError, toast, "
            "or a terminal error UI). A bare catch/console.error leaves the user "
            "with no feedback and a stuck recording."
        )


class TestB20VoiceBackendMimeTypes:
    """Bug 20 backend: voice upload endpoint must accept mobile MIME types."""

    def test_voice_upload_accepts_mobile_mime_types_or_uses_ffmpeg(self):
        from app.api import voice

        src = inspect.getsource(voice.voice_upload)
        # Also check _audio_ext which maps MIME types to extensions
        audio_ext_src = inspect.getsource(voice._audio_ext)
        full_src = src + audio_ext_src

        mobile_types = ["audio/mp4", "audio/m4a", "audio/aac", "audio/mpeg"]
        wildcard = "audio/*" in full_src
        uses_ffmpeg = "ffmpeg" in full_src or "_ffmpeg_to_wav" in full_src

        has_mobile_type = any(t in full_src for t in mobile_types)

        assert wildcard or uses_ffmpeg or has_mobile_type, (
            "Bug 20: /api/voice/upload must accept mobile MIME types such as "
            "audio/mp4, audio/m4a, audio/aac, audio/mpeg — OR use ffmpeg "
            "conversion (which is format-tolerant). "
            "Currently only audio/webm is reliably handled, causing mobile "
            "recordings to be rejected with 422 'unsupported format'."
        )

    def test_voice_upload_content_type_fallback_is_tolerant(self):
        from app.api import voice

        src = inspect.getsource(voice._audio_ext)
        # _audio_ext must handle unknown types gracefully (not raise, not return empty)
        # The current implementation falls back to .webm — that's fine for extensions,
        # but the MIME types for transcription must also be tolerant.
        # Check there is a fallback/default return path.
        assert "return" in src, "_audio_ext must have a return/fallback path"
        assert ".webm" in src or "webm" in src, (
            "_audio_ext must have a webm fallback for unknown content types "
            "so ffmpeg can still process the file."
        )


# ===========================================================================
# B21 — Desktop voice creates duplicate note
# ===========================================================================


class TestB21DuplicateNotePreventionFrontend:
    """Bug 21: recording a voice note creates two server notes — one from
    /api/voice/upload and one from syncManager.pushChanges() pushing the
    local pending Dexie note.

    Expected: after uploadVoice() succeeds, the local note must be marked
    syncStatus='synced' AND assigned the server id as serverId, so pushChanges()
    skips it. Alternatively, voice recordings never create a pending local note.
    """

    @staticmethod
    def _voice_capture_src() -> str:
        return _read_frontend("components/VoiceCapture.tsx")

    def test_upload_success_marks_local_note_synced(self):
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # Pattern 1: after upload success, update local note with syncStatus='synced'
        marks_synced = (
            "syncStatus: 'synced'" in code
            or 'syncStatus: "synced"' in code
        )
        # Pattern 2: voice recordings don't create a pending local note at all
        # (server-first path — no local note created until server responds)
        no_pending = "syncStatus: 'pending'" not in code and 'syncStatus: "pending"' not in code

        assert marks_synced or no_pending, (
            "Bug 21: VoiceCapture.tsx must either:\n"
            "  (a) Mark the local Dexie note as syncStatus='synced' after "
            "uploadVoice() succeeds (so pushChanges skips it), OR\n"
            "  (b) Never create a local pending note for voice recordings "
            "(server-first path).\n"
            "Currently both paths run in parallel — pushChanges() picks up "
            "the 'pending' note and creates a second server row."
        )

    def test_upload_success_assigns_server_id_to_local_note(self):
        src = self._voice_capture_src()
        code = _strip_comments(src)

        # After a successful voice upload the local note must get serverId = noteOut.id
        # so the sync engine can match them.
        assigns_server_id = re.search(
            r'serverId\s*:\s*(noteOut\.id|result\.id|data\.id|response\.id|serverNote\.id)',
            code,
        )
        # Alternative: no local note means serverId assignment is not needed
        no_pending = "syncStatus: 'pending'" not in code and 'syncStatus: "pending"' not in code

        assert assigns_server_id or no_pending, (
            "Bug 21: after uploadVoice() succeeds, the local Dexie note must "
            "be updated with serverId = <server_note_id>. Without this, "
            "pushChanges() cannot detect the overlap and pushes a duplicate. "
            "If you use a server-first path (no pending note), this test passes."
        )


@pytest.mark.asyncio
class TestB21DuplicateNoteBehavioral:
    """Behavioral: POST /api/notes with the same client_id twice must NOT create
    two rows — the second call should return the existing note or 409.

    This simulates the real-world duplicate: VoiceCapture POSTs to /api/voice/upload
    (server note A), then syncManager.pushChanges POSTs the same local note via
    /api/notes (server note B). Both carry the same client_id so the backend must
    dedup and return A instead of creating B.
    """

    async def test_second_notes_post_with_same_client_id_does_not_duplicate(
        self, client, auth_headers
    ):
        client_id = f"test-client-{uuid.uuid4().hex}"

        # 1. First POST /api/notes — simulates the server note created by /api/voice/upload
        first_resp = await client.post(
            "/api/notes",
            json={
                "content": "original voice note from server upload",
                "source_type": "voice",
                "client_id": client_id,
            },
            headers=auth_headers,
        )
        assert first_resp.status_code == 201, f"First note create failed: {first_resp.text}"
        first_note_id = first_resp.json()["id"]

        # 2. Second POST /api/notes with the same client_id
        # — simulates syncManager.pushChanges() pushing the pending local Dexie note
        second_resp = await client.post(
            "/api/notes",
            json={
                "content": "duplicate voice note",
                "source_type": "voice",
                "client_id": client_id,
            },
            headers=auth_headers,
        )
        # Must NOT create a second row — expect either:
        #   - 200/201 returning the EXISTING note (same id)
        #   - 409 Conflict
        assert second_resp.status_code in (200, 201, 409), (
            f"Unexpected status {second_resp.status_code}: {second_resp.text}"
        )
        if second_resp.status_code in (200, 201):
            returned_id = second_resp.json().get("id")
            assert str(returned_id) == str(first_note_id), (
                f"Bug 21: POST /api/notes with client_id={client_id!r} returned "
                f"a NEW note id {returned_id!r} instead of the existing one "
                f"{first_note_id!r}. Two server notes were created for one recording — "
                "the backend must dedup on client_id when the same user POSTs the "
                "same client_id twice."
            )

    async def test_voice_upload_then_notes_post_same_client_id_does_not_duplicate(
        self, client, auth_headers
    ):
        """Variant: voice/upload succeeded (mocked via a pre-seeded note with the
        same client_id); subsequent /api/notes push must not add a second row.

        Because /api/voice/upload requires Azure credentials (blob + speech),
        we simulate the post-upload state by pre-creating the note directly.
        """
        import io

        client_id = f"voice-client-{uuid.uuid4().hex}"

        # Pre-create note (as if voice/upload created it)
        seed_resp = await client.post(
            "/api/notes",
            json={
                "content": "transcribed voice note",
                "source_type": "voice",
                "client_id": client_id,
            },
            headers=auth_headers,
        )
        assert seed_resp.status_code == 201, f"Seed failed: {seed_resp.text}"
        seed_id = seed_resp.json()["id"]

        # syncManager.pushChanges() fires — same client_id
        push_resp = await client.post(
            "/api/notes",
            json={
                "content": "transcribed voice note",
                "source_type": "voice",
                "client_id": client_id,
            },
            headers=auth_headers,
        )
        assert push_resp.status_code in (200, 201, 409), (
            f"Unexpected {push_resp.status_code}: {push_resp.text}"
        )
        if push_resp.status_code in (200, 201):
            pushed_id = push_resp.json().get("id")
            assert str(pushed_id) == str(seed_id), (
                f"Bug 21: /api/notes with client_id={client_id!r} created a second "
                f"note (id={pushed_id!r}) instead of returning the existing one "
                f"(id={seed_id!r}). Backend must check: if a note with this client_id "
                "already exists for this user, return it (or 409) instead of inserting."
            )

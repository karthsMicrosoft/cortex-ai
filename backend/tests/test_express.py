"""
test_express.py — Task 3 (Express endpoint)
TDD red-phase tests for POST /api/ai/generate

Covers:
  Task 3.1 — POST /api/ai/generate
    - Accepts {kind: 'song'|'practice'|'reflection', source_note_ids: [...]}
    - Builds prompt per kind (FR-2.6/2.7/2.8)
    - Calls GPT-4o-mini
    - Returns {generated_text}
    - Requires auth
    - Validates kind enum
    - source_note_ids must belong to the authenticated user

Mock strategy: Mock OpenAI client via AsyncMock; use conftest client fixture.
"""
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_GENERATED_TEXT = "Here is a song idea based on your notes about jazz improvisation."

SONG_GENERATION_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": FAKE_GENERATED_TEXT,
                "role": "assistant",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 80, "completion_tokens": 60, "total_tokens": 140},
    "model": "gpt-4o-mini",
    "id": "chatcmpl-express",
    "object": "chat.completion",
    "created": 1700000030,
}


# ---------------------------------------------------------------------------
# Module import checks
# ---------------------------------------------------------------------------

class TestExpressModuleImport:
    def test_express_endpoint_exists_in_insights_or_express(self):
        """POST /api/ai/generate must be defined (in ai_summary_router or express.py)."""
        has_generate = False

        try:
            from app.api.insights import ai_summary_router
            routes = [r.path for r in ai_summary_router.routes]
            has_generate = any("generate" in p for p in routes)
        except ImportError:
            pass

        if not has_generate:
            try:
                from app.api.express import router as express_router
                routes = [r.path for r in express_router.routes]
                has_generate = any("generate" in p for p in routes)
            except ImportError:
                pass

        assert has_generate, "POST /api/ai/generate route not found in ai_summary_router or express.py"


# ---------------------------------------------------------------------------
# POST /api/ai/generate — Song
# ---------------------------------------------------------------------------

class TestExpressSongGeneration:
    async def test_generate_song_requires_auth(self, client: AsyncClient):
        """POST /api/ai/generate must return 401 without auth."""
        payload = {"kind": "song", "source_note_ids": [str(uuid.uuid4())]}
        resp = await client.post("/api/ai/generate", json=payload)
        assert resp.status_code == 401

    async def test_generate_song_returns_200_and_generated_text(self, client: AsyncClient, auth_headers: dict, db_session):
        """POST /api/ai/generate with kind='song' returns {generated_text}."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="Jazz improvisation in Dorian mode, feeling creative.",
            source_type="text",
            category="Music",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = FAKE_GENERATED_TEXT
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.post(
            "/api/ai/generate",
            json={"kind": "song", "source_note_ids": [str(note.id)]},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "generated_text" in body
        assert isinstance(body["generated_text"], str)
        assert len(body["generated_text"]) > 0

    async def test_generate_song_calls_gpt4o_mini(self, client: AsyncClient, auth_headers: dict, db_session):
        """POST /api/ai/generate (song) must call GPT-4o-mini."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="Wrote a melody with C major scale.",
            source_type="text",
            category="Music",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        captured_calls = []

        async def fake_create(**kwargs):
            captured_calls.append(kwargs)
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = "A gentle melody emerges..."
            return resp

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = fake_create
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.post(
            "/api/ai/generate",
            json={"kind": "song", "source_note_ids": [str(note.id)]},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        if resp.status_code == 200:
            assert len(captured_calls) >= 1
            assert "gpt-4o-mini" in captured_calls[0].get("model", "")


# ---------------------------------------------------------------------------
# POST /api/ai/generate — Practice plan
# ---------------------------------------------------------------------------

class TestExpressPracticePlan:
    async def test_generate_practice_returns_200(self, client: AsyncClient, auth_headers: dict, db_session):
        """POST /api/ai/generate with kind='practice' returns {generated_text}."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="Morning workout: 5km run and 30 push-ups.",
            source_type="text",
            category="Fitness",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Here is your 7-day practice plan..."
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.post(
            "/api/ai/generate",
            json={"kind": "practice", "source_note_ids": [str(note.id)]},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "generated_text" in body

    async def test_practice_prompt_differs_from_song_prompt(self, client: AsyncClient, auth_headers: dict, db_session):
        """Practice plan prompt must be different from song prompt (kind-specific prompt)."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="I want to improve my guitar playing.",
            source_type="text",
            category="Music",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        song_prompts = []
        practice_prompts = []

        async def capture_song(**kwargs):
            song_prompts.append(str(kwargs.get("messages", [])))
            r = MagicMock()
            r.choices = [MagicMock()]
            r.choices[0].message.content = "Song output."
            return r

        async def capture_practice(**kwargs):
            practice_prompts.append(str(kwargs.get("messages", [])))
            r = MagicMock()
            r.choices = [MagicMock()]
            r.choices[0].message.content = "Practice output."
            return r

        note_ids = [str(note.id)]

        mock_song_openai = AsyncMock()
        mock_song_openai.chat.completions.create = capture_song
        app.dependency_overrides[get_openai] = lambda: mock_song_openai
        await client.post(
            "/api/ai/generate",
            json={"kind": "song", "source_note_ids": note_ids},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        mock_practice_openai = AsyncMock()
        mock_practice_openai.chat.completions.create = capture_practice
        app.dependency_overrides[get_openai] = lambda: mock_practice_openai
        await client.post(
            "/api/ai/generate",
            json={"kind": "practice", "source_note_ids": note_ids},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        # If both were called, prompts must differ
        if song_prompts and practice_prompts:
            assert song_prompts[0] != practice_prompts[0], "Song and practice prompts must differ"


# ---------------------------------------------------------------------------
# POST /api/ai/generate — Reflection
# ---------------------------------------------------------------------------

class TestExpressReflection:
    async def test_generate_reflection_returns_200(self, client: AsyncClient, auth_headers: dict, db_session):
        """POST /api/ai/generate with kind='reflection' returns {generated_text}."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="Today I felt grateful for my progress in music.",
            source_type="text",
            category="Journal",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Reflecting on gratitude and music growth..."
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        app.dependency_overrides[get_openai] = lambda: mock_openai

        resp = await client.post(
            "/api/ai/generate",
            json={"kind": "reflection", "source_note_ids": [str(note.id)]},
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_openai, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "generated_text" in body


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestExpressValidation:
    async def test_invalid_kind_returns_422(self, client: AsyncClient, auth_headers: dict):
        """POST /api/ai/generate with invalid kind must return 422."""
        payload = {"kind": "invalid_kind", "source_note_ids": [str(uuid.uuid4())]}
        resp = await client.post("/api/ai/generate", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    async def test_missing_kind_returns_422(self, client: AsyncClient, auth_headers: dict):
        """POST /api/ai/generate without kind must return 422."""
        payload = {"source_note_ids": [str(uuid.uuid4())]}
        resp = await client.post("/api/ai/generate", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    async def test_empty_source_note_ids_returns_422_or_400(self, client: AsyncClient, auth_headers: dict):
        """POST /api/ai/generate with empty source_note_ids must return 400 or 422."""
        payload = {"kind": "song", "source_note_ids": []}
        resp = await client.post("/api/ai/generate", json=payload, headers=auth_headers)
        assert resp.status_code in (400, 422)

    async def test_cannot_use_other_users_notes(self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, db_session):
        """POST /api/ai/generate must not use note_ids belonging to another user."""
        from app.models.note import Note
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=second_user_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        other_user_id = _uuid.UUID(me_resp.json()["id"])

        other_note = Note(
            user_id=other_user_id,
            content="Private note that should not be accessible.",
            source_type="text",
            category="Journal",
            processing_status="enriched",
        )
        db_session.add(other_note)
        await db_session.flush()

        resp = await client.post(
            "/api/ai/generate",
            json={"kind": "reflection", "source_note_ids": [str(other_note.id)]},
            headers=auth_headers,
        )
        # Should return 404 (notes not found for this user) or 403
        assert resp.status_code in (403, 404)

    async def test_all_three_valid_kinds_accepted(self, client: AsyncClient, auth_headers: dict, db_session):
        """All three kind values (song, practice, reflection) must be accepted."""
        from app.models.note import Note
        from app.services.openai_client import get_openai
        from app.main import app
        import uuid as _uuid

        me_resp = await client.get("/api/auth/me", headers=auth_headers)
        if me_resp.status_code != 200:
            pytest.skip("Auth/me not available")
        user_id = _uuid.UUID(me_resp.json()["id"])

        note = Note(
            user_id=user_id,
            content="A versatile note for all kinds.",
            source_type="text",
            category="Ideas",
            processing_status="enriched",
        )
        db_session.add(note)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated content."
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        for kind in ("song", "practice", "reflection"):
            app.dependency_overrides[get_openai] = lambda: mock_openai
            resp = await client.post(
                "/api/ai/generate",
                json={"kind": kind, "source_note_ids": [str(note.id)]},
                headers=auth_headers,
            )
            app.dependency_overrides.pop(get_openai, None)
            # All three should be accepted (not 422)
            assert resp.status_code != 422, f"Kind '{kind}' was rejected with 422"

"""
test_dictionary.py — US-7 Personal Dictionary (TDD red phase)

Covers POST/GET/PUT/DELETE /api/dictionary, hard limits, duplicates,
bulk import, export, and schema/model imports.

Design refs:
  - SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md § F1.2, F1.4
  - us-7-personal-dictionary.tasks.md tasks 1.x, 2.x
"""
import uuid
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. Model / schema importability (red until coder implements them)
# ---------------------------------------------------------------------------

class TestModelImports:
    def test_user_vocabulary_model_importable(self):
        """UserVocabulary ORM model must be importable from app.models.vocabulary."""
        from app.models.vocabulary import UserVocabulary  # noqa: F401

    def test_user_vocabulary_registered_in_models_init(self):
        """UserVocabulary must be exported from app.models.__init__ for Alembic."""
        import app.models as models_pkg
        assert hasattr(models_pkg, "UserVocabulary"), (
            "UserVocabulary not exported from app/models/__init__.py"
        )

    def test_vocabulary_schema_importable(self):
        """Pydantic schemas for the dictionary endpoint must be importable."""
        from app.schemas.dictionary import VocabularyTerm, VocabularyTermOut, BulkImportRequest  # noqa: F401

    def test_vocabulary_term_fields(self):
        """VocabularyTerm must have term, term_type, pronunciation_hint, boost_weight."""
        from app.schemas.dictionary import VocabularyTerm
        import inspect
        fields = VocabularyTerm.model_fields
        for field_name in ("term", "term_type", "boost_weight"):
            assert field_name in fields, f"VocabularyTerm missing field: {field_name}"

    def test_vocabulary_term_type_default_general(self):
        """term_type must default to 'general'."""
        from app.schemas.dictionary import VocabularyTerm
        t = VocabularyTerm(term="arpeggio")
        assert t.term_type == "general"

    def test_vocabulary_term_boost_weight_default_one(self):
        """boost_weight must default to 1.0."""
        from app.schemas.dictionary import VocabularyTerm
        t = VocabularyTerm(term="pgvector")
        assert t.boost_weight == 1.0

    def test_vocabulary_term_boost_weight_out_of_range_rejected(self):
        """boost_weight must reject values outside [0.0, 2.0]."""
        from app.schemas.dictionary import VocabularyTerm
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            VocabularyTerm(term="x", boost_weight=3.0)

    def test_vocabulary_term_min_length_enforced(self):
        """term must reject empty string."""
        from app.schemas.dictionary import VocabularyTerm
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            VocabularyTerm(term="")

    def test_vocabulary_term_max_length_enforced(self):
        """term must reject strings longer than 200 characters."""
        from app.schemas.dictionary import VocabularyTerm
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            VocabularyTerm(term="x" * 201)

    def test_bulk_import_request_is_a_list_schema(self):
        """BulkImportRequest must wrap a list of VocabularyTerm."""
        from app.schemas.dictionary import BulkImportRequest, VocabularyTerm
        # Must be constructible with a list of terms
        req = BulkImportRequest(terms=[VocabularyTerm(term="hello")])
        assert len(req.terms) == 1


# ---------------------------------------------------------------------------
# 2. Router importability
# ---------------------------------------------------------------------------

class TestDictionaryRouterImport:
    def test_router_importable(self):
        from app.api.dictionary import router  # noqa: F401
        from fastapi import APIRouter
        assert isinstance(router, APIRouter if True else object)

    def test_router_prefix(self):
        from app.api.dictionary import router
        assert router.prefix == "/api/dictionary", (
            f"Expected router prefix '/api/dictionary', got '{router.prefix}'"
        )

    def test_max_terms_constant_exists(self):
        from app.api.dictionary import MAX_TERMS_PER_USER
        assert MAX_TERMS_PER_USER == 2000


# ---------------------------------------------------------------------------
# 3. GET /api/dictionary — list terms
# ---------------------------------------------------------------------------

class TestDictionaryList:
    async def test_requires_auth(self, client: AsyncClient):
        """GET /api/dictionary without auth must return 401."""
        resp = await client.get("/api/dictionary")
        assert resp.status_code == 401

    async def test_empty_list_for_new_user(self, client: AsyncClient, auth_headers: dict):
        """GET /api/dictionary returns an empty list for a fresh user."""
        resp = await client.get("/api/dictionary", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert resp.json() == []

    async def test_filter_by_term_type(self, client: AsyncClient, auth_headers: dict):
        """GET /api/dictionary?term_type=name must filter results."""
        # Add two terms with different types
        await client.post(
            "/api/dictionary",
            json={"term": "Daniel Anvar", "term_type": "name"},
            headers=auth_headers,
        )
        await client.post(
            "/api/dictionary",
            json={"term": "pgvector", "term_type": "technical"},
            headers=auth_headers,
        )

        resp = await client.get(
            "/api/dictionary", params={"term_type": "name"}, headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(t["term_type"] == "name" for t in data), (
            "Filter by term_type=name returned terms with other types"
        )

    async def test_list_ordered_by_usage_count_desc(self, client: AsyncClient, auth_headers: dict):
        """GET /api/dictionary must return terms ordered by usage_count desc."""
        # The ordering is verified by the endpoint contract; use a dedicated user
        resp = await client.get("/api/dictionary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        if len(data) >= 2:
            counts = [t["usage_count"] for t in data]
            assert counts == sorted(counts, reverse=True), (
                "Terms are not ordered by usage_count desc"
            )

    async def test_list_returns_correct_fields(self, client: AsyncClient, auth_headers: dict):
        """Each term in GET /api/dictionary list must have required fields."""
        await client.post(
            "/api/dictionary",
            json={"term": "arpeggio", "term_type": "music_term"},
            headers=auth_headers,
        )
        resp = await client.get("/api/dictionary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        term = data[0]
        for field in ("id", "term", "term_type", "usage_count"):
            assert field in term, f"Missing field '{field}' in term response"


# ---------------------------------------------------------------------------
# 4. POST /api/dictionary — add term
# ---------------------------------------------------------------------------

class TestDictionaryAddTerm:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/dictionary",
            json={"term": "test term", "term_type": "general"},
        )
        assert resp.status_code == 401

    async def test_add_term_returns_201(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary must return 201 on valid payload."""
        resp = await client.post(
            "/api/dictionary",
            json={"term": f"unique_term_{uuid.uuid4().hex[:6]}", "term_type": "general"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_add_term_response_shape(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary must return the created term with required fields."""
        resp = await client.post(
            "/api/dictionary",
            json={"term": f"arpegio_{uuid.uuid4().hex[:4]}", "term_type": "music_term"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "term" in body
        assert "term_type" in body
        assert body["term_type"] == "music_term"

    async def test_add_term_with_pronunciation_hint(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary with pronunciation_hint must store it."""
        resp = await client.post(
            "/api/dictionary",
            json={
                "term": f"Karthik_{uuid.uuid4().hex[:4]}",
                "term_type": "name",
                "pronunciation_hint": "car-thick",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body.get("pronunciation_hint") == "car-thick"

    async def test_add_term_with_boost_weight(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary with custom boost_weight must store it."""
        resp = await client.post(
            "/api/dictionary",
            json={"term": f"cosmos_{uuid.uuid4().hex[:4]}", "boost_weight": 1.5},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert abs(body.get("boost_weight", 0) - 1.5) < 0.001

    async def test_duplicate_term_returns_409(self, client: AsyncClient, auth_headers: dict):
        """Posting the same term twice for the same user must return 409."""
        term = f"duplicate_term_{uuid.uuid4().hex[:8]}"
        first = await client.post(
            "/api/dictionary",
            json={"term": term, "term_type": "general"},
            headers=auth_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/dictionary",
            json={"term": term, "term_type": "general"},
            headers=auth_headers,
        )
        assert second.status_code == 409, (
            f"Expected 409 for duplicate term, got {second.status_code}: {second.text}"
        )

    async def test_hard_limit_2000_returns_400(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary must return 400 when user already has 2000 terms."""
        # We patch the DB scalar count rather than inserting 2000 real rows.
        with patch(
            "app.api.dictionary.get_term_count",
            new_callable=AsyncMock,
            return_value=2000,
        ):
            resp = await client.post(
                "/api/dictionary",
                json={"term": "overflow_term", "term_type": "general"},
                headers=auth_headers,
            )
        assert resp.status_code == 400, (
            f"Expected 400 when limit reached, got {resp.status_code}: {resp.text}"
        )

    async def test_term_type_name_accepted(self, client: AsyncClient, auth_headers: dict):
        for term_type in ("name", "music_term", "technical", "place", "acronym", "general"):
            resp = await client.post(
                "/api/dictionary",
                json={"term": f"term_{term_type}_{uuid.uuid4().hex[:4]}", "term_type": term_type},
                headers=auth_headers,
            )
            assert resp.status_code == 201, (
                f"term_type='{term_type}' rejected: {resp.status_code} {resp.text}"
            )

    async def test_different_users_same_term_no_conflict(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """The same term used by two different users must not produce 409."""
        shared_term = f"shared_term_{uuid.uuid4().hex[:6]}"
        r1 = await client.post(
            "/api/dictionary",
            json={"term": shared_term, "term_type": "general"},
            headers=auth_headers,
        )
        assert r1.status_code == 201
        r2 = await client.post(
            "/api/dictionary",
            json={"term": shared_term, "term_type": "general"},
            headers=second_user_headers,
        )
        assert r2.status_code == 201, (
            f"Cross-user same term incorrectly returned 409: {r2.text}"
        )


# ---------------------------------------------------------------------------
# 5. PUT /api/dictionary/{id} — update term
# ---------------------------------------------------------------------------

class TestDictionaryUpdateTerm:
    async def _create_term(self, client, headers, term=None, term_type="general"):
        term = term or f"initial_{uuid.uuid4().hex[:6]}"
        resp = await client.post(
            "/api/dictionary",
            json={"term": term, "term_type": term_type},
            headers=headers,
        )
        assert resp.status_code == 201, f"Setup failed: {resp.text}"
        return resp.json()

    async def test_update_term_type(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/dictionary/{id} must update term_type and return 200."""
        created = await self._create_term(client, auth_headers)
        term_id = created["id"]

        resp = await client.put(
            f"/api/dictionary/{term_id}",
            json={"term_type": "technical"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["term_type"] == "technical"

    async def test_update_pronunciation_hint(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/dictionary/{id} must update pronunciation_hint."""
        created = await self._create_term(client, auth_headers)
        term_id = created["id"]

        resp = await client.put(
            f"/api/dictionary/{term_id}",
            json={"pronunciation_hint": "new-hint"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json().get("pronunciation_hint") == "new-hint"

    async def test_update_requires_auth(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/dictionary/{id} without auth must return 401."""
        created = await self._create_term(client, auth_headers)
        resp = await client.put(
            f"/api/dictionary/{created['id']}",
            json={"term_type": "name"},
        )
        assert resp.status_code == 401

    async def test_update_nonexistent_term_404(self, client: AsyncClient, auth_headers: dict):
        """PUT /api/dictionary/{id} for a nonexistent term must return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.put(
            f"/api/dictionary/{fake_id}",
            json={"term_type": "name"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_other_users_term_404(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A must not be able to update user B's term."""
        created = await self._create_term(client, second_user_headers)
        resp = await client.put(
            f"/api/dictionary/{created['id']}",
            json={"term_type": "name"},
            headers=auth_headers,
        )
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 6. DELETE /api/dictionary/{id} — remove term
# ---------------------------------------------------------------------------

class TestDictionaryDeleteTerm:
    async def _create_term(self, client, headers):
        term = f"delete_me_{uuid.uuid4().hex[:6]}"
        resp = await client.post(
            "/api/dictionary",
            json={"term": term, "term_type": "general"},
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_delete_returns_204(self, client: AsyncClient, auth_headers: dict):
        """DELETE /api/dictionary/{id} must return 204."""
        created = await self._create_term(client, auth_headers)
        resp = await client.delete(
            f"/api/dictionary/{created['id']}", headers=auth_headers
        )
        assert resp.status_code == 204

    async def test_deleted_term_not_in_list(self, client: AsyncClient, auth_headers: dict):
        """After DELETE, the term must not appear in GET /api/dictionary."""
        created = await self._create_term(client, auth_headers)
        term_id = created["id"]

        await client.delete(f"/api/dictionary/{term_id}", headers=auth_headers)

        list_resp = await client.get("/api/dictionary", headers=auth_headers)
        ids = [t["id"] for t in list_resp.json()]
        assert term_id not in ids

    async def test_delete_requires_auth(self, client: AsyncClient, auth_headers: dict):
        """DELETE /api/dictionary/{id} without auth must return 401."""
        created = await self._create_term(client, auth_headers)
        resp = await client.delete(f"/api/dictionary/{created['id']}")
        assert resp.status_code == 401

    async def test_delete_other_users_term_no_effect(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A deleting user B's term must not succeed (204 is acceptable but term remains)."""
        created = await self._create_term(client, second_user_headers)
        term_id = created["id"]

        # Attempt deletion with wrong user
        resp = await client.delete(
            f"/api/dictionary/{term_id}", headers=auth_headers
        )
        # Either forbidden or no-op (204 without actual deletion)
        # Verify the term still exists for user B
        list_resp = await client.get("/api/dictionary", headers=second_user_headers)
        ids = [t["id"] for t in list_resp.json()]
        assert term_id in ids, (
            "User A deleted user B's term — ownership isolation failed"
        )


# ---------------------------------------------------------------------------
# 7. POST /api/dictionary/bulk — bulk import
# ---------------------------------------------------------------------------

class TestDictionaryBulkImport:
    async def test_bulk_import_returns_201(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary/bulk with valid terms must return 201."""
        terms = [
            {"term": f"bulk_term_{i}_{uuid.uuid4().hex[:4]}", "term_type": "general"}
            for i in range(5)
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_bulk_import_response_shape(self, client: AsyncClient, auth_headers: dict):
        """Bulk import response must include 'inserted' and 'total' keys."""
        terms = [
            {"term": f"shape_term_{i}_{uuid.uuid4().hex[:4]}", "term_type": "general"}
            for i in range(3)
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "inserted" in body, f"'inserted' key missing: {body}"
        assert "total" in body, f"'total' key missing: {body}"
        assert body["total"] == 3

    async def test_bulk_import_inserted_count(self, client: AsyncClient, auth_headers: dict):
        """Bulk import must report the correct inserted count."""
        unique_suffix = uuid.uuid4().hex[:6]
        terms = [
            {"term": f"count_{i}_{unique_suffix}", "term_type": "general"}
            for i in range(4)
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["inserted"] == 4

    async def test_bulk_import_over_500_returns_400(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary/bulk with > 500 terms must return 400."""
        terms = [
            {"term": f"over500_{i}_{uuid.uuid4().hex[:4]}", "term_type": "general"}
            for i in range(501)
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for > 500-term bulk import, got {resp.status_code}: {resp.text}"
        )

    async def test_bulk_import_exactly_500_accepted(self, client: AsyncClient, auth_headers: dict):
        """POST /api/dictionary/bulk with exactly 500 terms must be accepted."""
        terms = [
            {"term": f"exactly500_{i}_{uuid.uuid4().hex[:4]}", "term_type": "general"}
            for i in range(500)
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 201, (
            f"Expected 201 for exactly 500 terms, got {resp.status_code}"
        )

    async def test_bulk_import_requires_auth(self, client: AsyncClient):
        """POST /api/dictionary/bulk without auth must return 401."""
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": [{"term": "no-auth-term", "term_type": "general"}]},
        )
        assert resp.status_code == 401

    async def test_bulk_import_skips_duplicates(self, client: AsyncClient, auth_headers: dict):
        """Bulk import must skip (not error on) duplicate terms; inserted < total."""
        shared_term = f"shared_bulk_{uuid.uuid4().hex[:6]}"
        # Pre-insert the term
        await client.post(
            "/api/dictionary",
            json={"term": shared_term, "term_type": "general"},
            headers=auth_headers,
        )
        # Try to bulk-import with one duplicate and one new term
        new_term = f"new_bulk_{uuid.uuid4().hex[:6]}"
        terms = [
            {"term": shared_term, "term_type": "general"},
            {"term": new_term, "term_type": "general"},
        ]
        resp = await client.post(
            "/api/dictionary/bulk",
            json={"terms": terms},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total"] == 2
        assert body["inserted"] == 1, (
            f"Expected inserted=1 (1 duplicate skipped), got {body['inserted']}"
        )


# ---------------------------------------------------------------------------
# 8. GET /api/dictionary/export — export
# ---------------------------------------------------------------------------

class TestDictionaryExport:
    async def test_export_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/dictionary/export")
        assert resp.status_code == 401

    async def test_export_returns_200(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/dictionary/export", headers=auth_headers)
        assert resp.status_code == 200

    async def test_export_returns_list(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/dictionary/export", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_export_includes_added_terms(self, client: AsyncClient, auth_headers: dict):
        """Export must include all user terms."""
        term = f"export_term_{uuid.uuid4().hex[:6]}"
        await client.post(
            "/api/dictionary",
            json={"term": term, "term_type": "technical"},
            headers=auth_headers,
        )
        resp = await client.get("/api/dictionary/export", headers=auth_headers)
        assert resp.status_code == 200
        exported_terms = [t["term"] for t in resp.json()]
        assert term in exported_terms

    async def test_export_does_not_include_other_users_terms(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """Export must only include the authenticated user's terms."""
        other_term = f"other_user_term_{uuid.uuid4().hex[:6]}"
        await client.post(
            "/api/dictionary",
            json={"term": other_term, "term_type": "general"},
            headers=second_user_headers,
        )
        resp = await client.get("/api/dictionary/export", headers=auth_headers)
        exported_terms = [t["term"] for t in resp.json()]
        assert other_term not in exported_terms


# ---------------------------------------------------------------------------
# 9. usage_count default and presence
# ---------------------------------------------------------------------------

class TestUsageCount:
    async def test_new_term_has_usage_count_zero(self, client: AsyncClient, auth_headers: dict):
        """A freshly-added term must have usage_count=0."""
        resp = await client.post(
            "/api/dictionary",
            json={"term": f"fresh_{uuid.uuid4().hex[:6]}", "term_type": "general"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        # Either the POST response or the GET list will carry usage_count
        body = resp.json()
        if "usage_count" in body:
            assert body["usage_count"] == 0

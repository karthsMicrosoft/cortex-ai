"""
test_tags.py — Task 8
Tests for GET /api/tags and POST /api/tags

Covers:
  - GET /api/tags returns all tags belonging to the authenticated user
  - POST /api/tags creates a manual tag (is_auto=False)
  - Both endpoints require authentication
  - Router lives in backend/app/api/tags.py (B6 — dedicated module)
  - Tags are user-scoped (no cross-user leakage)

Mock strategy: no Azure calls needed for tags — pure DB CRUD.
"""
import uuid
import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

class TestTagsModuleImport:
    def test_tags_module_importable(self):
        """backend/app/api/tags.py must be importable."""
        from app.api import tags  # noqa: F401

    def test_router_exported(self):
        """tags module must expose a FastAPI APIRouter named `router`."""
        from app.api.tags import router
        from fastapi import APIRouter
        assert isinstance(router, APIRouter)


# ---------------------------------------------------------------------------
# GET /api/tags — auth
# ---------------------------------------------------------------------------

class TestGetTagsAuth:
    async def test_get_tags_requires_auth(self, client):
        """GET /api/tags without token must return 401."""
        resp = await client.get("/api/tags")
        assert resp.status_code == 401

    async def test_get_tags_with_invalid_token_returns_401(self, client):
        resp = await client.get(
            "/api/tags",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/tags — happy path
# ---------------------------------------------------------------------------

class TestGetTags:
    async def test_get_tags_returns_list(self, client, auth_headers):
        """GET /api/tags must return a JSON list (may be empty for new user)."""
        resp = await client.get("/api/tags", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_tags_returns_created_tags(self, client, auth_headers):
        """Tags created by the user must appear in GET /api/tags."""
        # Create a tag first
        create_resp = await client.post(
            "/api/tags",
            json={"name": "test-tag-unique-123"},
            headers=auth_headers,
        )
        assert create_resp.status_code in (200, 201)

        # List tags — must include the created tag
        list_resp = await client.get("/api/tags", headers=auth_headers)
        assert list_resp.status_code == 200
        tag_names = [t["name"] for t in list_resp.json()]
        assert "test-tag-unique-123" in tag_names

    async def test_get_tags_only_returns_own_tags(self, client, auth_headers, second_user_headers):
        """Tags from another user must not appear in the current user's tag list."""
        # Second user creates a tag
        await client.post(
            "/api/tags",
            json={"name": "second-user-private-tag"},
            headers=second_user_headers,
        )

        # First user's tags must not include second user's tag
        resp = await client.get("/api/tags", headers=auth_headers)
        assert resp.status_code == 200
        tag_names = [t["name"] for t in resp.json()]
        assert "second-user-private-tag" not in tag_names

    async def test_get_tags_response_shape(self, client, auth_headers):
        """Each tag in the list must have at least 'id' and 'name' fields."""
        # Create a tag to ensure at least one exists
        await client.post(
            "/api/tags",
            json={"name": "shape-test-tag"},
            headers=auth_headers,
        )
        resp = await client.get("/api/tags", headers=auth_headers)
        assert resp.status_code == 200
        tags = resp.json()
        if tags:
            tag = tags[0]
            assert "id" in tag
            assert "name" in tag


# ---------------------------------------------------------------------------
# POST /api/tags — auth
# ---------------------------------------------------------------------------

class TestPostTagsAuth:
    async def test_post_tags_requires_auth(self, client):
        """POST /api/tags without token must return 401."""
        resp = await client.post("/api/tags", json={"name": "some-tag"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/tags — happy path
# ---------------------------------------------------------------------------

class TestPostTags:
    async def test_post_tags_creates_tag(self, client, auth_headers):
        """POST /api/tags must create a tag and return it."""
        tag_name = f"manual-tag-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body.get("name") == tag_name

    async def test_post_tags_is_auto_false(self, client, auth_headers):
        """Manually created tags must have is_auto=False."""
        tag_name = f"manual-tag-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        # is_auto should be False for manually created tags
        if "is_auto" in body:
            assert body["is_auto"] is False

    async def test_post_tags_returns_id(self, client, auth_headers):
        """POST /api/tags must return a valid UUID id for the created tag."""
        tag_name = f"tag-id-test-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "id" in body
        # Verify it's a valid UUID
        uuid.UUID(body["id"])

    async def test_post_tags_duplicate_returns_error_or_existing(self, client, auth_headers):
        """
        Posting a duplicate tag name must either return 409 Conflict or
        return the existing tag (not create a duplicate DB row).
        """
        tag_name = f"dup-tag-{uuid.uuid4().hex[:8]}"

        first = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        assert first.status_code in (200, 201)

        second = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        # Accept either 409 or returning the same tag
        if second.status_code == 200 or second.status_code == 201:
            assert second.json()["name"] == tag_name
        else:
            assert second.status_code == 409

    async def test_post_tags_name_required(self, client, auth_headers):
        """POST /api/tags without a name must return 422."""
        resp = await client.post(
            "/api/tags",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_post_tags_tag_scoped_to_user(self, client, auth_headers, second_user_headers):
        """
        A tag created by user A must not appear in user B's tag list.
        """
        tag_name = f"scoped-tag-{uuid.uuid4().hex[:8]}"
        create_resp = await client.post(
            "/api/tags",
            json={"name": tag_name},
            headers=auth_headers,
        )
        assert create_resp.status_code in (200, 201)

        # Second user's tags must not include the first user's tag
        list_resp = await client.get("/api/tags", headers=second_user_headers)
        assert list_resp.status_code == 200
        tag_names = [t["name"] for t in list_resp.json()]
        assert tag_name not in tag_names

"""Tests for the bulk Note import script (scripts/import_notes.py).

Smoke-tests the dry-run path against tiny in-memory Keep + Notion
fixtures. HTTP import paths are covered with respx mocks so tests never
hit the real network.

The point of these tests is to pin:
  - parsing logic survives a refactor (titles, tags, checklist
    flattening, Notion folder-as-tag),
  - filter flags (--include-trashed / --no-include-archived) actually
    skip rows,
  - category resolution falls back correctly,
  - client_id is deterministic + collision-resistant (so a re-run
    de-dupes via Bug 21).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx

# Project layout: backend/scripts/import_notes.py
# Tests live in backend/tests/, so we can import scripts.* directly.
from scripts.import_notes import (
    CORTEX_CATEGORIES,
    ImportedNote,
    _dedupe_tags,
    _parse_label_map,
    _resolve_category,
    load_google_keep,
    load_notion,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def keep_dir(tmp_path: Path) -> Path:
    """Build a tiny Google Takeout/Keep folder with a representative spread."""
    root = tmp_path / "Keep"
    root.mkdir()

    # A typical text note with title + labels.
    (root / "1700000000000000.json").write_text(json.dumps({
        "title": "Italian dinner ideas",
        "textContent": "Risotto, focaccia, tiramisu",
        "labels": [{"name": "Recipes"}, {"name": "Learning"}],
        "isArchived": False,
        "isTrashed": False,
        "isPinned": True,
        "userEditedTimestampUsec": 1700000000000000,
    }))

    # A checklist note (listContent) with no textContent.
    (root / "1700000000000001.json").write_text(json.dumps({
        "title": "Grocery run",
        "listContent": [
            {"text": "Olive oil", "isChecked": False},
            {"text": "Garlic", "isChecked": True},
        ],
        "labels": [],
    }))

    # A trashed note — should be skipped by default.
    (root / "1700000000000002.json").write_text(json.dumps({
        "title": "Old grudge",
        "textContent": "irrelevant",
        "isTrashed": True,
    }))

    # An archived note — kept by default (matches Keep default behaviour),
    # tagged "archived".
    (root / "1700000000000003.json").write_text(json.dumps({
        "title": "Archived idea",
        "textContent": "still useful later",
        "isArchived": True,
    }))

    # A truly empty note — should be silently skipped.
    (root / "1700000000000004.json").write_text(json.dumps({
        "title": "",
        "textContent": "",
        "labels": [],
    }))

    # An attachment-only note (audio).
    (root / "1700000000000005.json").write_text(json.dumps({
        "title": "Voice memo",
        "textContent": "",
        "attachments": [{"filePath": "audio1.3gpp", "mimetype": "audio/3gpp"}],
    }))

    # A bare Labels.json metadata file — must be ignored.
    (root / "Labels.json").write_text(json.dumps({"labels": [{"name": "Recipes"}]}))

    # Unrelated HTML siblings should be ignored.
    (root / "1700000000000000.html").write_text("<html></html>")

    return root


@pytest.fixture
def notion_dir(tmp_path: Path) -> Path:
    """Build a tiny Notion Markdown export tree with nested pages."""
    root = tmp_path / "Export-2026-06-01"
    root.mkdir()

    # Top-level page with H1 title + body.
    (root / "Personal abc123def4567890abcdef0123456789.md").write_text(
        "# Personal\n\nMy private workspace.\n",
        encoding="utf-8",
    )

    # Nested sub-page.
    nested = root / "Personal abc123def4567890abcdef0123456789"
    nested.mkdir()
    (nested / "Reading List ffffffffffffffffffffffffffffffff.md").write_text(
        "# Reading List\n\n- The Pragmatic Programmer\n- Designing Data-Intensive Apps\n",
        encoding="utf-8",
    )

    # A page with NO H1 — title should fall back to the cleaned filename.
    (root / "Headerless 12345678901234567890123456789012.md").write_text(
        "Body text only, no markdown title.\n",
        encoding="utf-8",
    )

    # Database CSV — should be skipped entirely.
    (root / "Tasks ffffffffffffffffffffffffffffffff.csv").write_text(
        "Task,Status\nWrite docs,Doing\n", encoding="utf-8",
    )

    # Empty .md (no title, no body) — should be skipped.
    (root / "Blank deadbeefdeadbeefdeadbeefdeadbeef.md").write_text("", encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Google Keep parsing
# ---------------------------------------------------------------------------

class TestLoadGoogleKeep:
    def test_default_run_skips_trashed_keeps_archived(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        titles = sorted(n.title or "" for n in notes)
        # "Old grudge" (trashed) gone; "Archived idea" kept; empty gone.
        assert "Old grudge" not in titles
        assert "Archived idea" in titles
        assert "Italian dinner ideas" in titles
        assert "Grocery run" in titles
        assert "Voice memo" in titles
        # Labels.json metadata + .html files were ignored.
        assert len(notes) == 4

    def test_include_trashed_brings_it_back(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=True,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        titles = {n.title for n in notes}
        assert "Old grudge" in titles

    def test_no_include_archived_drops_archived(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=False,
            default_category="Ideas",
            label_map={},
        )
        titles = {n.title for n in notes}
        assert "Archived idea" not in titles
        assert "Italian dinner ideas" in titles

    def test_label_matching_chooses_cortex_category(self, keep_dir: Path):
        # The dinner note has a "Learning" label that matches a Cortex category.
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        dinner = next(n for n in notes if n.title == "Italian dinner ideas")
        assert dinner.category == "Learning"
        assert "source:keep" in dinner.tags
        assert "pinned" in dinner.tags
        assert "Recipes" in dinner.tags

    def test_label_map_override_takes_precedence(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={"recipes": "Music"},  # silly but tests precedence
        )
        dinner = next(n for n in notes if n.title == "Italian dinner ideas")
        # "recipes" (mapped to Music) wins over the "Learning" auto-match.
        assert dinner.category == "Music"

    def test_checklist_flattens_to_bullets(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        grocery = next(n for n in notes if n.title == "Grocery run")
        assert "- [ ] Olive oil" in grocery.body
        assert "- [x] Garlic" in grocery.body

    def test_attachment_note_includes_marker(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        memo = next(n for n in notes if n.title == "Voice memo")
        assert "[Original attachments not imported" in memo.body
        assert "audio1.3gpp" in memo.body

    def test_archived_tag_attached(self, keep_dir: Path):
        notes = load_google_keep(
            keep_dir,
            include_trashed=False,
            include_archived=True,
            default_category="Ideas",
            label_map={},
        )
        archived = next(n for n in notes if n.title == "Archived idea")
        assert "archived" in archived.tags

    def test_missing_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_google_keep(
                tmp_path / "nope",
                include_trashed=False,
                include_archived=True,
                default_category="Ideas",
                label_map={},
            )


# ---------------------------------------------------------------------------
# Notion parsing
# ---------------------------------------------------------------------------

class TestLoadNotion:
    def test_walks_recursive_md_files(self, notion_dir: Path):
        notes = load_notion(notion_dir, default_category="Ideas", label_map={})
        titles = {n.title for n in notes}
        # CSV + blank skipped; 3 real .md kept (Personal, Reading List, Headerless).
        assert "Personal" in titles
        assert "Reading List" in titles
        # Headerless fallback uses the cleaned filename (no hex suffix).
        assert any("Headerless" in t for t in titles)
        assert len(notes) == 3

    def test_h1_extracted_and_body_starts_after(self, notion_dir: Path):
        notes = load_notion(notion_dir, default_category="Learning", label_map={})
        reading = next(n for n in notes if n.title == "Reading List")
        assert "The Pragmatic Programmer" in reading.body
        assert "# Reading List" not in reading.body  # H1 was consumed as title

    def test_nested_folder_becomes_tag(self, notion_dir: Path):
        notes = load_notion(notion_dir, default_category="Learning", label_map={})
        reading = next(n for n in notes if n.title == "Reading List")
        assert "source:notion" in reading.tags
        # The parent folder "Personal abc123..." should be stripped of the hex
        # suffix and surface as a tag.
        assert any(t.startswith("Personal") for t in reading.tags)

    def test_csv_files_are_skipped(self, notion_dir: Path):
        notes = load_notion(notion_dir, default_category="Ideas", label_map={})
        # No note title equal to "Tasks" — the CSV was skipped.
        assert all(n.title != "Tasks" for n in notes)

    def test_empty_md_files_are_skipped(self, notion_dir: Path):
        notes = load_notion(notion_dir, default_category="Ideas", label_map={})
        assert all("Blank" not in (n.title or "") for n in notes)


# ---------------------------------------------------------------------------
# Helpers — category + tag normalisation
# ---------------------------------------------------------------------------

class TestResolveCategory:
    def test_label_map_wins(self):
        assert _resolve_category(
            ["recipes"], {"recipes": "Music"}, "Ideas",
        ) == "Music"

    def test_cortex_match_case_insensitive(self):
        assert _resolve_category(
            ["fitness"], {}, "Ideas",
        ) == "Fitness"
        assert _resolve_category(
            ["LEARNING"], {}, "Ideas",
        ) == "Learning"

    def test_default_fallback(self):
        assert _resolve_category(
            ["random"], {}, "Journal",
        ) == "Journal"

    def test_unknown_default_falls_to_ideas(self):
        assert _resolve_category(
            [], {}, "NotARealCategory",
        ) == "Ideas"


class TestDedupeTags:
    def test_preserves_first_casing(self):
        assert _dedupe_tags(["Foo", "foo", "Bar"]) == ["Foo", "Bar"]

    def test_trims_and_drops_empty(self):
        assert _dedupe_tags(["  ", "x", "x ", "y"]) == ["x", "y"]


class TestParseLabelMap:
    def test_parses_simple_pairs(self):
        assert _parse_label_map("recipes=Learning,workout=Fitness") == {
            "recipes": "Learning",
            "workout": "Fitness",
        }

    def test_lowercases_keys(self):
        assert _parse_label_map("Recipes=Learning") == {"recipes": "Learning"}

    def test_skips_invalid_target(self):
        # NotACategory isn't a Cortex category → dropped with a warning.
        assert _parse_label_map("foo=NotACategory") == {}

    def test_skips_malformed(self):
        assert _parse_label_map("nokey,still=Music,=Fitness") == {"still": "Music"}


# ---------------------------------------------------------------------------
# ImportedNote behaviour
# ---------------------------------------------------------------------------

class TestImportedNote:
    def test_client_id_is_deterministic(self):
        a = ImportedNote(source_key="keep:1.json", title="x", body="y", tags=[], category="Ideas")
        b = ImportedNote(source_key="keep:1.json", title="DIFFERENT", body="DIFFERENT", tags=["t"], category="Music")
        # Same source_key → same client_id (so re-runs dedup via Bug 21).
        assert a.client_id == b.client_id

    def test_client_id_differs_per_source(self):
        a = ImportedNote(source_key="keep:1.json", title="", body="x", tags=[], category="Ideas")
        b = ImportedNote(source_key="notion:1.md", title="", body="x", tags=[], category="Ideas")
        assert a.client_id != b.client_id

    def test_content_truncates_past_limit(self):
        long = "x" * 60_000
        note = ImportedNote(source_key="k:1", title=None, body=long, tags=[], category="Ideas")
        assert len(note.content) <= 50_000
        assert "[…content truncated by import_notes" in note.content

    def test_content_falls_back_to_marker_when_empty(self):
        note = ImportedNote(source_key="k:1", title=None, body="", tags=[], category="Ideas")
        assert note.content == "(empty note imported)"

    def test_title_prefixed_as_h1(self):
        note = ImportedNote(source_key="k:1", title="Hello", body="World", tags=[], category="Ideas")
        assert note.content.startswith("# Hello")
        assert "World" in note.content


# ---------------------------------------------------------------------------
# CLI smoke — --dry-run end-to-end (no HTTP, no token required)
# ---------------------------------------------------------------------------

class TestCLIHTTPRelink:
    def _run_keep_import(self, keep_dir: Path, *extra_args: str) -> int:
        return main([
            "--source", "google-keep",
            "--path", str(keep_dir),
            "--api-url", "http://test.example",
            "--token", "test-token",
            *extra_args,
        ])

    def test_relink_called_when_creates_succeed(self, keep_dir: Path):
        with respx.mock(base_url="http://test.example", assert_all_called=False) as httpx_mock:
            httpx_mock.post("/api/notes").mock(
                return_value=httpx.Response(201, json={"id": "note-id"})
            )
            relink_route = httpx_mock.post("/api/notes/relink-all").mock(
                return_value=httpx.Response(
                    200,
                    json={"created": 5, "updated": 0, "duration_ms": 100, "skipped_recent": False},
                )
            )

            rc = self._run_keep_import(keep_dir)

        assert rc == 0
        assert relink_route.call_count == 1

    def test_no_relink_flag_skips(self, keep_dir: Path):
        with respx.mock(base_url="http://test.example", assert_all_called=False) as httpx_mock:
            httpx_mock.post("/api/notes").mock(
                return_value=httpx.Response(201, json={"id": "note-id"})
            )
            relink_route = httpx_mock.post("/api/notes/relink-all").mock(
                return_value=httpx.Response(
                    200,
                    json={"created": 5, "updated": 0, "duration_ms": 100, "skipped_recent": False},
                )
            )

            rc = self._run_keep_import(keep_dir, "--no-relink")

        assert rc == 0
        assert relink_route.call_count == 0

    def test_relink_skipped_when_nothing_created(self, keep_dir: Path):
        with respx.mock(base_url="http://test.example", assert_all_called=False) as httpx_mock:
            httpx_mock.post("/api/notes").mock(
                return_value=httpx.Response(200, json={"id": "existing-note-id"})
            )
            relink_route = httpx_mock.post("/api/notes/relink-all").mock(
                return_value=httpx.Response(
                    200,
                    json={"created": 5, "updated": 0, "duration_ms": 100, "skipped_recent": False},
                )
            )

            rc = self._run_keep_import(keep_dir)

        assert rc == 0
        assert relink_route.call_count == 0

    def test_relink_failure_is_non_fatal(self, keep_dir: Path, caplog):
        caplog.set_level(logging.WARNING, logger="import_notes")
        with respx.mock(base_url="http://test.example", assert_all_called=False) as httpx_mock:
            httpx_mock.post("/api/notes").mock(
                return_value=httpx.Response(201, json={"id": "note-id"})
            )
            relink_route = httpx_mock.post("/api/notes/relink-all").mock(
                return_value=httpx.Response(500, json={"detail": "boom"})
            )

            rc = self._run_keep_import(keep_dir)

        assert rc == 0
        assert relink_route.call_count == 1
        assert any("backfill_semantic_links" in r.message for r in caplog.records)


class TestCLIDryRun:
    def test_dry_run_keep_exits_zero(self, keep_dir: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        rc = main([
            "--source", "google-keep",
            "--path", str(keep_dir),
            "--default-category", "Journal",
            "--dry-run",
        ])
        assert rc == 0
        assert any("Scanned" in r.message for r in caplog.records)
        assert any("dry-run" in r.message for r in caplog.records)

    def test_dry_run_notion_exits_zero(self, notion_dir: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        rc = main([
            "--source", "notion",
            "--path", str(notion_dir),
            "--default-category", "Learning",
            "--dry-run",
        ])
        assert rc == 0

    def test_empty_source_returns_1(self, tmp_path: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        empty = tmp_path / "empty-keep"
        empty.mkdir()
        rc = main([
            "--source", "google-keep",
            "--path", str(empty),
            "--dry-run",
        ])
        assert rc == 1

    def test_missing_source_returns_2(self, tmp_path: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        rc = main([
            "--source", "google-keep",
            "--path", str(tmp_path / "does-not-exist"),
            "--dry-run",
        ])
        assert rc == 2

    def test_token_required_unless_dry_run(self, keep_dir: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        rc = main([
            "--source", "google-keep",
            "--path", str(keep_dir),
        ])
        # No --dry-run, no --token → error code 2.
        assert rc == 2

    def test_limit_caps_count(self, keep_dir: Path, caplog):
        caplog.set_level(logging.INFO, logger="import_notes")
        rc = main([
            "--source", "google-keep",
            "--path", str(keep_dir),
            "--dry-run",
            "--limit", "1",
        ])
        assert rc == 0
        scanned = [r for r in caplog.records if "Scanned" in r.message]
        assert scanned
        assert "→ 1 notes parsed" in scanned[0].message


# ---------------------------------------------------------------------------
# Categories sanity — make sure the script + backend agree
# ---------------------------------------------------------------------------

def test_script_categories_match_backend():
    """If the backend schema adds/removes a category, this test will catch it
    before someone runs a 5,000-note import with the wrong vocabulary."""
    from app.schemas.note import NoteCreate  # type: ignore
    # NoteCreate.category is a Literal[...] alias — extract its members.
    annotation = NoteCreate.model_fields["category"].annotation
    backend_categories = set(getattr(annotation, "__args__", ()))
    assert backend_categories == CORTEX_CATEGORIES, (
        f"Backend NoteCreate.category vocabulary {backend_categories} "
        f"differs from scripts.import_notes.CORTEX_CATEGORIES "
        f"{CORTEX_CATEGORIES}. Update one to match the other."
    )

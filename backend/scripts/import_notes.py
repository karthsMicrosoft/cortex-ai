"""Bulk-import notes from Google Keep + Notion exports into Cortex.

Runs locally against the deployed Cortex backend (or a local dev backend).
Reads exports on disk, POSTs each note to ``POST /api/notes``, lets the
backend pipeline handle clean-up + categorisation + embedding.

WHY THIS EXISTS
---------------
The user's existing notes live in Google Keep and Notion. The Cortex
``POST /api/notes`` endpoint is the workhorse for text imports — it
accepts JSON ``{content, source_type, category, tags, client_id}`` and
schedules the background AI pipeline. This script just wraps a directory
walk + payload conversion around that endpoint.

EXPORT FORMATS WE SUPPORT
-------------------------
- **Google Keep** (via Google Takeout):
    Settings → Data & privacy → Download your data → Keep only.
    The ZIP contains ``Takeout/Keep/`` with one ``.json`` per note
    (and matching ``.html`` we ignore).  JSON shape::

        {
          "title": "...",
          "textContent": "...",
          "labels": [{"name": "Recipes"}, ...],
          "isArchived": false,
          "isTrashed": false,
          "isPinned": false,
          "userEditedTimestampUsec": 1700000000000000,
          "attachments": [{"filePath": "...", "mimetype": "audio/3gpp"}],
          "listContent": [{"text": "Buy milk", "isChecked": false}]
        }

  Notes with ``listContent`` (checklists) are flattened to a
  bullet-list body. Trashed notes are skipped by default
  (``--include-trashed`` to import them). Attachments are NOT uploaded
  (would need /api/upload + audio transcode) — we just leave a TODO
  comment in the body so you can re-attach manually.

- **Notion** (via Workspace → Settings → Export):
    Choose "Markdown & CSV" + "Include subpages". The ZIP unpacks into a
    nested folder tree mirroring your workspace. Each page is one
    ``*.md`` file (and a sibling folder for nested pages). Title comes
    from the first ``# H1`` line (Notion always writes one), body is the
    rest. Database CSVs (``*.csv``) are skipped — they would need a
    different importer (one row per note) which is out of scope.

CATEGORY MAPPING
----------------
Cortex categories are fixed: Music, Fitness, Journal, Ideas, Spiritual,
Learning. Mapping rules:
  - ``--default-category`` flag (default: Ideas) is applied to every
    note unless the source-side label matches a Cortex category name
    case-insensitively (e.g. Keep label "fitness" → "Fitness").
  - Custom mapping via ``--label-map "label1=Music,label2=Journal"``.
The backend pipeline will run its own categorisation pass anyway and
may overwrite the import-time guess, so this is just a starting hint.

IDEMPOTENCY
-----------
Each note's ``client_id`` is a deterministic ``sha256`` of
``"source:relative_path"``. Re-running the script returns the existing
note (Bug 21 dedup behaviour in ``POST /api/notes``) instead of creating
duplicates. So you can run it, fix a typo, and re-run safely.

CONCURRENCY + RATE LIMITS
-------------------------
Five concurrent POSTs by default (``--concurrency``). The Container App
backend handles this fine. If you hit 429s on a fresh deploy with a cold
pipeline, drop to ``--concurrency 2``. Exponential backoff is wired for
5xx / network errors.

USAGE
-----
    # Mint an access token first. Easiest path:
    #   1. Sign in to https://gentle-river-06c1e4e10.7.azurestaticapps.net
    #   2. DevTools → Console → JSON.parse(localStorage.getItem('cortex_refresh'))
    #      ... actually no — refresh token only. Use this instead:
    #   2. DevTools → Application → Local Storage → cortex_refresh
    #   3. POST to /api/auth/refresh with that token to get a fresh access_token
    #      (or just copy the access token from the Authorization header of any
    #       /api/* network call in DevTools → Network tab.)

    # Google Keep
    python -m scripts.import_notes \
      --source google-keep \
      --path ~/Downloads/Takeout/Keep \
      --api-url https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io \
      --token "eyJ..." \
      --default-category Journal \
      --dry-run

    # Notion (after extracting the export ZIP)
    python -m scripts.import_notes \
      --source notion \
      --path ~/Downloads/Export-2026-06-01 \
      --api-url https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io \
      --token "eyJ..." \
      --default-category Learning

    # Local dev
    python -m scripts.import_notes \
      --source notion \
      --path ./test-notion-export \
      --api-url http://localhost:8000 \
      --token "$(python -c 'import requests; print(requests.post("http://localhost:8000/api/auth/login", json={"email":"me@x.com","password":"..."}).json()["access_token"])')"

EXIT CODES
----------
- 0: at least one note was created (or --dry-run scanned cleanly)
- 1: nothing imported (empty source dir, bad token, etc.)
- 2: invalid arguments / unreadable source dir
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("import_notes")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORTEX_CATEGORIES = {"Music", "Fitness", "Journal", "Ideas", "Spiritual", "Learning"}
CORTEX_CATEGORIES_LOWER = {c.lower(): c for c in CORTEX_CATEGORIES}

# POST /api/notes caps content at 50_000 chars (SEC-05). We truncate slightly
# below that and prepend a clear marker so the user can find + manually rejoin.
MAX_CONTENT = 49_500
TRUNCATED_NOTE = "\n\n[…content truncated by import_notes — original was longer than 50K chars]"


# ---------------------------------------------------------------------------
# Note model — common shape for both sources
# ---------------------------------------------------------------------------

@dataclass
class ImportedNote:
    source_key: str            # e.g. "keep:1700000000000000.json" or "notion:Path/To/Page.md"
    title: Optional[str]
    body: str
    tags: list[str]
    category: str              # one of CORTEX_CATEGORIES

    @property
    def client_id(self) -> str:
        return "import:" + hashlib.sha256(self.source_key.encode("utf-8")).hexdigest()[:32]

    @property
    def content(self) -> str:
        parts = []
        if self.title:
            parts.append(f"# {self.title}\n")
        parts.append(self.body.strip())
        text = "\n".join(parts).strip()
        if len(text) > MAX_CONTENT:
            text = text[:MAX_CONTENT] + TRUNCATED_NOTE
        return text or "(empty note imported)"


# ---------------------------------------------------------------------------
# Source: Google Keep (Google Takeout)
# ---------------------------------------------------------------------------

def load_google_keep(
    root: Path,
    *,
    include_trashed: bool,
    include_archived: bool,
    default_category: str,
    label_map: dict[str, str],
) -> list[ImportedNote]:
    notes: list[ImportedNote] = []
    if not root.is_dir():
        raise FileNotFoundError(f"Google Keep source dir not found: {root}")

    for json_path in sorted(root.glob("*.json")):
        # Takeout sometimes puts a Labels.json metadata file at the top.
        if json_path.name.lower() == "labels.json":
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Skipping unreadable JSON: %s", json_path.name)
            continue

        if not isinstance(data, dict):
            continue
        if data.get("isTrashed") and not include_trashed:
            continue
        if data.get("isArchived") and not include_archived:
            continue

        title = (data.get("title") or "").strip() or None
        text = (data.get("textContent") or "").strip()
        list_content = data.get("listContent") or []
        if list_content and not text:
            text = "\n".join(
                f"- [{'x' if item.get('isChecked') else ' '}] {item.get('text', '').strip()}"
                for item in list_content
                if isinstance(item, dict)
            )

        labels = [
            (lbl.get("name") or "").strip()
            for lbl in (data.get("labels") or [])
            if isinstance(lbl, dict) and (lbl.get("name") or "").strip()
        ]

        attachments = data.get("attachments") or []
        if attachments:
            attachment_note = "\n".join(
                f"  - {a.get('filePath', '?')} ({a.get('mimetype', '?')})"
                for a in attachments
                if isinstance(a, dict)
            )
            text = (text + f"\n\n[Original attachments not imported — see Takeout for raw files:\n{attachment_note}]").strip()

        category = _resolve_category(labels, label_map, default_category)
        tags = ["source:keep", *labels]
        if data.get("isPinned"):
            tags.append("pinned")
        if data.get("isArchived"):
            tags.append("archived")
        if data.get("isTrashed"):
            tags.append("trashed")

        if not text and not title:
            # Skip truly empty notes
            continue

        notes.append(
            ImportedNote(
                source_key=f"keep:{json_path.name}",
                title=title,
                body=text,
                tags=_dedupe_tags(tags),
                category=category,
            )
        )

    return notes


# ---------------------------------------------------------------------------
# Source: Notion (Markdown & CSV export)
# ---------------------------------------------------------------------------

# Notion appends a 32-hex hash to every file/folder name (e.g.
# "My Page abc123...md"). Strip it for the title fallback.
_NOTION_ID_SUFFIX = re.compile(r"\s*[0-9a-f]{32}(?=\.md$|/)", re.IGNORECASE)

def load_notion(
    root: Path,
    *,
    default_category: str,
    label_map: dict[str, str],
) -> list[ImportedNote]:
    notes: list[ImportedNote] = []
    if not root.is_dir():
        raise FileNotFoundError(f"Notion source dir not found: {root}")

    for md_path in sorted(root.rglob("*.md")):
        try:
            raw = md_path.read_text(encoding="utf-8")
        except OSError:
            log.warning("Skipping unreadable .md: %s", md_path)
            continue

        # Strip a leading BOM if present
        if raw.startswith("\ufeff"):
            raw = raw.lstrip("\ufeff")

        lines = raw.splitlines()
        title: Optional[str] = None
        had_h1 = False
        body_start = 0
        # First non-empty line is the H1 in Notion's export
        for i, line in enumerate(lines):
            if line.strip():
                if line.startswith("# "):
                    title = line[2:].strip()
                    had_h1 = True
                    body_start = i + 1
                break

        # Fallback: derive title from filename (minus the 32-hex page id)
        if not title:
            stem = md_path.stem
            cleaned = _NOTION_ID_SUFFIX.sub("", stem + ".md").rstrip(".md").strip()
            title = cleaned or stem

        body = "\n".join(lines[body_start:]).strip()

        # Skip placeholder pages: no real H1 AND no body. Notion writes one
        # ``.md`` per page, including empty stub pages; we don't want to
        # import those as "(empty note imported)" rows.
        if not body and not had_h1:
            continue

        # Tags: derive from path components (folder names = parent pages)
        rel = md_path.relative_to(root)
        path_labels = [
            _NOTION_ID_SUFFIX.sub("", part + "/").rstrip("/").strip()
            for part in rel.parts[:-1]
        ]
        path_labels = [p for p in path_labels if p]

        category = _resolve_category(path_labels, label_map, default_category)
        tags = ["source:notion", *path_labels]

        notes.append(
            ImportedNote(
                source_key=f"notion:{rel.as_posix()}",
                title=title,
                body=body,
                tags=_dedupe_tags(tags),
                category=category,
            )
        )

    return notes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_category(
    labels: list[str],
    label_map: dict[str, str],
    default_category: str,
) -> str:
    """Pick a Cortex category from the source labels.

    Order of precedence:
      1. Explicit --label-map entry (case-insensitive).
      2. Source label that matches a Cortex category name (case-insensitive).
      3. --default-category fallback.
    """
    for raw in labels:
        key = raw.strip().lower()
        if not key:
            continue
        mapped = label_map.get(key)
        if mapped and mapped in CORTEX_CATEGORIES:
            return mapped
        if key in CORTEX_CATEGORIES_LOWER:
            return CORTEX_CATEGORIES_LOWER[key]
    if default_category in CORTEX_CATEGORIES:
        return default_category
    return "Ideas"


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        key = t.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out


def _parse_label_map(spec: str) -> dict[str, str]:
    """Parse "label1=Music,label2=Journal" into {label1: Music, label2: Journal}."""
    out: dict[str, str] = {}
    for piece in (spec or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "=" not in piece:
            log.warning("Ignoring malformed --label-map entry (no '='): %s", piece)
            continue
        k, v = piece.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k or v not in CORTEX_CATEGORIES:
            log.warning(
                "Ignoring --label-map entry %r (target must be one of %s)",
                piece,
                ", ".join(sorted(CORTEX_CATEGORIES)),
            )
            continue
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# HTTP — POST each note to /api/notes
# ---------------------------------------------------------------------------

class ImportError_(RuntimeError):
    """Domain-specific error so the CLI can format it cleanly."""


@dataclass
class Counters:
    created: int = 0
    skipped: int = 0     # 200 OK on a pre-existing client_id (Bug 21 dedup)
    failed: int = 0


async def _post_one(
    client: httpx.AsyncClient,
    note: ImportedNote,
    *,
    api_url: str,
    token: str,
    extra_tags: list[str],
    sem: asyncio.Semaphore,
    counters: Counters,
) -> None:
    payload = {
        "content": note.content,
        "source_type": "text",
        "category": note.category,
        "tags": _dedupe_tags([*note.tags, *extra_tags]),
        "client_id": note.client_id,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with sem:
        # Retry with exponential backoff for transient failures.
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = await client.post(
                    f"{api_url.rstrip('/')}/api/notes",
                    json=payload,
                    headers=headers,
                    timeout=httpx.Timeout(30.0, read=60.0),
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue

            if resp.status_code == 201:
                counters.created += 1
                return
            if resp.status_code == 200:
                # Existing note returned via client_id dedup — counts as success.
                counters.skipped += 1
                return
            if resp.status_code in (401, 403):
                # Token problem — fail fast; don't burn rate limit on retries.
                counters.failed += 1
                log.error("Auth failure (HTTP %s) for %s — check --token", resp.status_code, note.source_key)
                return
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                # Transient: retry
                log.warning(
                    "Transient HTTP %s on %s (attempt %d), backing off",
                    resp.status_code, note.source_key, attempt + 1,
                )
                await asyncio.sleep(2**attempt)
                continue

            counters.failed += 1
            log.error(
                "Permanent HTTP %s on %s: %s",
                resp.status_code, note.source_key, (resp.text or "")[:200],
            )
            return

        counters.failed += 1
        log.error("Gave up on %s after retries: %s", note.source_key, last_exc)


async def _post_all(
    notes: list[ImportedNote],
    *,
    api_url: str,
    token: str,
    extra_tags: list[str],
    concurrency: int,
) -> Counters:
    counters = Counters()
    sem = asyncio.Semaphore(max(1, concurrency))
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(
                _post_one(
                    client, n,
                    api_url=api_url, token=token,
                    extra_tags=extra_tags, sem=sem, counters=counters,
                )
            )
            for n in notes
        ]
        # Periodic progress logging
        done = 0
        for fut in asyncio.as_completed(tasks):
            await fut
            done += 1
            if done % 25 == 0 or done == len(notes):
                log.info(
                    "Progress: %d/%d (created=%d skipped=%d failed=%d)",
                    done, len(notes), counters.created, counters.skipped, counters.failed,
                )
    return counters


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="import_notes",
        description="Bulk-import notes from Google Keep + Notion exports into Cortex.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--source", required=True, choices=["google-keep", "notion"],
                    help="Which export format to read.")
    ap.add_argument("--path", required=True, type=Path,
                    help="Directory containing the export. "
                         "Keep: the .../Takeout/Keep folder. "
                         "Notion: the extracted export root.")
    ap.add_argument("--api-url", required=False, default="http://localhost:8000",
                    help="Base URL of the Cortex backend (default: localhost dev).")
    ap.add_argument("--token", required=False, default=None,
                    help="Bearer access token. Required unless --dry-run.")
    ap.add_argument("--default-category", default="Ideas",
                    choices=sorted(CORTEX_CATEGORIES),
                    help="Cortex category to fall back to when no label maps.")
    ap.add_argument("--label-map", default="",
                    help='Comma-separated label→category overrides, e.g. '
                         '"recipes=Learning,workout=Fitness".')
    ap.add_argument("--tag", action="append", default=[],
                    help="Extra tag to attach to every imported note "
                         "(repeatable). E.g. --tag '2024-archive'.")
    ap.add_argument("--concurrency", type=int, default=5,
                    help="Concurrent POSTs (default 5).")
    ap.add_argument("--include-trashed", action="store_true",
                    help="Google Keep only: also import trashed notes.")
    ap.add_argument("--include-archived", action="store_true",
                    help="Google Keep only: also import archived notes "
                         "(default: on; set --no-include-archived to skip).")
    ap.add_argument("--no-include-archived", dest="include_archived",
                    action="store_false")
    ap.set_defaults(include_archived=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse + count without POSTing. No token required.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only import the first N notes (smoke-test).")
    return ap


def load_notes(args) -> list[ImportedNote]:
    label_map = _parse_label_map(args.label_map)
    if args.source == "google-keep":
        notes = load_google_keep(
            args.path,
            include_trashed=args.include_trashed,
            include_archived=args.include_archived,
            default_category=args.default_category,
            label_map=label_map,
        )
    elif args.source == "notion":
        notes = load_notion(
            args.path,
            default_category=args.default_category,
            label_map=label_map,
        )
    else:
        raise ImportError_(f"Unknown source: {args.source}")
    if args.limit:
        notes = notes[: args.limit]
    return notes


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)

    try:
        notes = load_notes(args)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2

    log.info("Scanned %s → %d notes parsed", args.path, len(notes))
    if not notes:
        log.warning("Nothing to import — empty source or all notes filtered out.")
        return 1

    # Show a small preview so the user can sanity-check before committing.
    preview_n = min(3, len(notes))
    log.info("Preview of first %d note(s):", preview_n)
    for n in notes[:preview_n]:
        snippet = n.content.replace("\n", " ")[:140]
        log.info("  - [%s] %s | tags=%s | %s%s",
                 n.category, (n.title or "(no title)")[:60],
                 ",".join(n.tags), snippet,
                 "…" if len(n.content) > 140 else "")

    if args.dry_run:
        log.info("--dry-run: stopping before any HTTP POST.")
        return 0

    if not args.token:
        log.error("--token is required unless --dry-run.")
        return 2

    counters = asyncio.run(
        _post_all(
            notes,
            api_url=args.api_url,
            token=args.token,
            extra_tags=args.tag or [],
            concurrency=args.concurrency,
        )
    )
    log.info(
        "Done. created=%d  skipped(dedup)=%d  failed=%d",
        counters.created, counters.skipped, counters.failed,
    )
    return 0 if (counters.created + counters.skipped) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# Importing notes from Google Keep + Notion

This is the fastest way to bulk-import notes from other platforms into
Cortex. It uses `backend/scripts/import_notes.py` — a small CLI that
reads the export on disk and POSTs each note to `POST /api/notes`. The
existing backend pipeline then cleans up, categorises, and embeds each
note in the background.

---

## 1 — Export your data

### Google Keep
1. Go to https://takeout.google.com.
2. **Deselect all**, then re-select **Keep** only.
3. Choose **ZIP** + **2 GB** (most Keep exports are tiny).
4. Wait for the email, download, unzip.
5. The notes live in `Takeout/Keep/*.json` — one JSON per note.

### Notion
1. In Notion: **Settings & members → Settings → Export all workspace content**.
2. Format: **Markdown & CSV**. ✅ **Include subpages**. ✅ **Include
   databases as Markdown**.
3. Wait for the email, download, unzip.
4. The notes are `*.md` files in a nested folder tree mirroring your
   workspace.

---

## 2 — Mint an access token

The script needs a bearer token to call `POST /api/notes`. Easiest path:

1. Sign in to https://gentle-river-06c1e4e10.7.azurestaticapps.net on a
   desktop browser.
2. Open DevTools → **Network** tab.
3. Click anywhere in the app that hits the API (e.g. open Library).
4. Pick any `/api/*` request → **Headers** → copy the value of the
   `Authorization` header **after** `Bearer ` (it's a long `eyJ…` JWT).

The token is valid for ~30 minutes. If a long import outlives it, you'll
see HTTP 401 in the logs — just grab a fresh token and re-run. The
script de-dupes by `client_id`, so a second run skips notes that already
landed.

---

## 3 — Run the importer

From the `backend/` directory:

```bash
# Dry run first — sanity-check parsing without POSTing anything.
python -m scripts.import_notes \
  --source google-keep \
  --path ~/Downloads/Takeout/Keep \
  --default-category Journal \
  --dry-run

# Real run — Google Keep
python -m scripts.import_notes \
  --source google-keep \
  --path ~/Downloads/Takeout/Keep \
  --api-url https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io \
  --token "eyJ..." \
  --default-category Journal

# Real run — Notion
python -m scripts.import_notes \
  --source notion \
  --path ~/Downloads/Export-2026-06-01 \
  --api-url https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io \
  --token "eyJ..." \
  --default-category Learning
```

### What gets imported

| Source | Captured | Skipped |
|---|---|---|
| Keep `.json` | title, text body, checklist items (flattened to `- [ ]` bullets), labels (as Cortex tags), pinned/archived flags | trashed notes (use `--include-trashed` to include), `Labels.json` metadata, sibling `.html` files, attachments (left as a marker — see below) |
| Notion `.md` | first `# H1` as title (or filename fallback), rest as body, parent-folder names as Cortex tags | database `.csv` files, truly-empty `.md` placeholders |

### Categories

Cortex has six fixed categories: **Music, Fitness, Journal, Ideas,
Spiritual, Learning**. The script picks one per note in this order:

1. Explicit `--label-map "label1=Music,label2=Fitness"` override
   (case-insensitive on the left, must match a Cortex category on the
   right).
2. The source label matches a Cortex category name case-insensitively
   (e.g. Keep label "fitness" → "Fitness").
3. `--default-category` flag (default: `Ideas`).

The backend AI pipeline runs its own categorisation pass after the
import, so the chosen category is just a starting hint — it can be
overwritten by the pipeline.

### Idempotency

Each note's `client_id` is a deterministic `sha256` of
`"<source>:<relative_path>"`. Re-running the script returns the
existing note (Bug 21 dedup behaviour) instead of creating duplicates.
So you can run, fix a typo / change `--default-category`, and re-run
safely.

### Attachments

Audio + image attachments in Keep are **not** uploaded automatically —
they would need `/api/upload` + an audio transcode pass. The script
leaves a marker in the note body listing the original `filePath` +
`mimetype`, so you can locate the file in your Takeout download and
re-attach manually via the Capture screen.

If you want bulk attachment upload, file a follow-up and we'll extend
the script.

### Notion databases / table pages

`.csv` files (Notion database exports) are skipped. They need a
different importer — one row per Cortex note, with column → tag
mapping. Out of scope for this script; ping back if you need it.

### Auto re-link after import

After all note POSTs land, the script makes one final POST to
`/api/notes/relink-all`. This gives the earliest-imported notes (which
had no peers at create time) their composite-scored semantic links.

The endpoint is rate-limited to once every 5 minutes. If the response
shows `skipped_recent=true`, run
`python -m scripts.backfill_semantic_links --email <yours>` later to
force a rebuild. Pass `--no-relink` to opt out of the automatic step.

---

## 4 — Verify

After the import finishes, the log prints `created / skipped / failed`
counts. To verify in the app:

- Open `/library` → all imported notes appear (newest-first if the
  import happened recently).
- Filter by the `source:keep` or `source:notion` tag chip to see
  exactly what came in.
- Open one of the imported notes → the AI pipeline may take 5–30s to
  finish background processing (clean transcript, categorisation,
  embedding). Refresh once and the indicators flip from `raw` to
  `enriched`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `HTTP 401` repeatedly | Token expired | Mint a fresh token, re-run. Dedup will skip already-imported notes. |
| `HTTP 429` repeatedly | Rate limit | Drop `--concurrency` to 2. |
| `Permanent HTTP 422` | Note content > 50K chars even after truncation | Script auto-truncates at ~49.5K with a marker — split the note manually before re-running. |
| Notion: nested page imported with empty title | Source `.md` had no `# H1` AND a filename like `Untitled abc123…md` | Open the page in Notion, give it a real title, re-export. |
| Keep: voice notes have no audio | Attachments aren't uploaded by this script | Use the Capture screen to re-record or upload the original `.3gpp`/`.m4a` file from `Takeout/Keep`. |
| Want to start over | `client_id` dedup keeps you from re-importing | Delete the previously-imported notes in `/library` first (select-mode + bulk delete), then re-run. |

---

## Tests

`backend/tests/test_import_notes.py` — 40 unit tests covering parsing,
filters, category resolution, idempotency, CLI exit codes, and mocked HTTP. Run
with:

```bash
cd backend
python -m pytest tests/test_import_notes.py --no-cov -v
```

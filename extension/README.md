# Cortex Clip — Chrome MV3 extension

A minimal Chrome extension that sends the current tab's URL to your Cortex
Second Brain library via `POST /api/import/url`.

## Security model

The extension stores a **limited-scope clip token** (JWT with `scope: "clip"`)
in `chrome.storage.local`. That token can ONLY call:

- `POST /api/import/url` — save a URL.
- `POST /api/notes` — create a free-form note.

Every other backend route (delete note, export, change password, sync pull,
etc.) rejects scoped tokens with HTTP 403. This means a compromise of the
extension's storage cannot exfiltrate your library or hijack your account.

We deliberately do NOT reuse the full session JWT/refresh-cookie pair from
the web app — those grant unrestricted access and don't belong in extension
storage.

## End-user install (once published)

1. Install the extension from the Chrome Web Store.
2. Open the Cortex web app, go to **Settings → Browser Extension**, and click
   "Mint clip token". Copy the token.
3. Click the Cortex Clip toolbar icon, expand "Set / replace clip token",
   paste the token, and click **Save token**.
4. On any page you want to keep, click the toolbar icon and press **Save**.

## Developer install (unpacked, MVP)

1. Go to `chrome://extensions/`.
2. Toggle **Developer mode** on (top right).
3. Click **Load unpacked** and pick this `extension/` directory.
4. The "Cortex Clip" icon should appear in your toolbar.

## Tests

```pwsh
cd extension
npm install
npm test
```

Vitest + jsdom; mocks `chrome.storage.local`, `chrome.tabs.query`, and
`fetch`.

## Follow-ups (not in this PR)

- Real branded icons (current placeholders are 1×1 transparent PNGs — Chrome
  warns but still loads them).
- Firefox / Safari ports.
- An OAuth-based mint flow so users don't have to hand-paste a token.
- Right-click "Save link to Cortex" context menu.

# Cortex iOS Shortcuts Integration

## What this is
Use your iPhone's Action Button (15 Pro Max) or any iOS Shortcut to instantly start a voice recording in the installed Cortex PWA. The Shortcut opens Cortex directly to capture mode, so you can start a voice note without hunting for the app icon.

## Pick a path based on your default browser

iOS Shortcuts has two ways to launch the PWA, and the right one depends on whether your default browser is Safari:

| Your default browser | Use this Shortcut action | Auto-start mic? |
|---|---|---|
| **Safari** | `Open URLs` → `/?autostart=1` | ✅ Yes, no extra setup |
| **Edge / Chrome / Firefox / DuckDuckGo / anything else** | `Open App` → `Cortex` + flip a Settings toggle | ✅ Yes, after one-time toggle |

> **Why?** iOS Shortcuts' `Open URLs` action ALWAYS hands the URL to your default browser. If your default isn't Safari, the URL opens in (say) Edge as a regular webpage — your installed home-screen PWA is never launched. The `Open App` action is browser-agnostic and lists every installed app, including home-screen PWAs.

## Prerequisites
- iPhone running iOS 16.4+ (iOS 17+ recommended for Action Button).
- Cortex PWA already added to the home screen (`Safari` → `Share` → `Add to Home Screen`).
- You've granted Cortex microphone permission at least once.

---

## Path A — Default browser is Safari (simplest)

### 1. Build the Shortcut
1. Open the `Shortcuts` app.
2. Tap `+` (top right) to create a new shortcut.
3. Search for `Open URLs` and add it.
4. Paste the URL:

   ```text
   https://gentle-river-06c1e4e10.7.azurestaticapps.net/?autostart=1
   ```

5. Tap the title at the top (default `Shortcut`) and rename to `Record Cortex Note`.
6. Pick an icon (Cortex uses indigo `#4F46E5`; a microphone glyph reads well).
7. Tap `Done`.

### 2. Wire to a button (pick one)
- **Action Button (iPhone 15 Pro / 15 Pro Max):** `Settings` → `Action Button` → `Shortcut` → `Record Cortex Note`.
- **Back Tap (any iPhone with iOS 14+):** `Settings` → `Accessibility` → `Touch` → `Back Tap` → `Double Tap` (or `Triple Tap`) → pick `Record Cortex Note`.
- **Control Center (iOS 16+):** `Settings` → `Control Center` → add `Shortcuts` → tap `Shortcuts` in Control Center → pick `Record Cortex Note`.

Tap your button → Cortex opens in standalone mode and starts recording immediately.

---

## Path B — Default browser is Edge / Chrome / anything other than Safari

### 1. Flip the Settings toggle (one time)
In the installed Cortex PWA:

1. Open `Settings`.
2. Find `Reminders` → `Use record screen as launcher` → turn it **ON**.

This makes Cortex auto-start the mic any time the app opens at `/`. Without this toggle, `Open App` would land you on the regular home screen (you'd then tap Record manually).

### 2. Build the Shortcut
1. Open the `Shortcuts` app.
2. Tap `+` (top right) to create a new shortcut.
3. Search for `Open App` and add it.
4. Tap `Choose` → scroll your apps → pick `Cortex` (the home-screen PWA appears in this list with its own icon).
5. Tap the title at the top (default `Shortcut`) and rename to `Record Cortex Note`.
6. Pick an icon (mic glyph in indigo `#4F46E5`).
7. Tap `Done`.

### 3. Wire to a button
Same as Path A above (Action Button / Back Tap / Control Center).

Tap your button → Cortex launches → mic starts immediately, regardless of your default browser.

> **To turn this off:** disable the Settings toggle. Subsequent launches go to the normal capture page; you'd tap Record manually.

---

## Troubleshooting

### Path A — the URL opens in Safari but not in the installed PWA
- Confirm the PWA is installed to the home screen, not just bookmarked.
- iOS sometimes opens the first launch in Safari then "remembers". Open the home-screen Cortex icon once, then trigger the shortcut again.
- On older iOS (<16.4), PWAs and shortcuts don't always cooperate. Upgrading iOS resolves it.

### Path A — the URL opens in Edge / Chrome instead of the PWA
- Your default browser is set to something other than Safari. Switch to Path B above.

### The mic doesn't start automatically
- Open Cortex via the home-screen icon first, allow microphone, and take a quick recording manually so iOS caches the permission grant.
- Re-trigger the shortcut.
- For Path B: confirm the `Use record screen as launcher` toggle is ON in Cortex Settings.

### "Permission denied" toast in the app
- iOS Safari/PWA mic permission can reset if you haven't used the app for a while.
- `Settings` → `Safari` → `Advanced` → `Website Data` → search `cortex` → confirm storage isn't cleared.
- Alternatively, `Settings` → `Safari` → `Microphone` → set to `Allow`.

### The `Open App` picker doesn't show Cortex
- The PWA must be installed to the home screen (not just bookmarked). Re-install via Safari → Share → Add to Home Screen.
- Try restarting the Shortcuts app — iOS sometimes caches the installed-apps list.

### I want the recording to use a specific note category
- Future enhancement (deferred). Today the launch always lands in the default capture flow.

## How it works under the hood

- **Path A:** the deep link sets `?autostart=1` in the query string. When `CapturePage.tsx` mounts and sees the flag, it calls the same mic-start handler the user normally taps. The manifest's `scope: "/"` means iOS recognizes the URL as belonging to the installed PWA and launches it in standalone mode, with no Safari chrome.

- **Path B:** the `Open App` action launches the PWA at its `start_url` (`/`). Inside `CapturePage`, the auto-start check also reads `localStorage.cortex_launcher_record`; when the Settings toggle is on, the page treats the launch as if `?autostart=1` were present. No URL routing, no default-browser involvement.

## Privacy
- The Shortcut only opens an app or a URL. No data leaves your device until you record and save.
- All transcription and storage uses your Cortex account on the existing Azure backend.
- The launcher-record toggle is stored in `localStorage` on your device only — it never syncs to the server.

---
_Rounds 35–36 — see PROGRESS.md for context._

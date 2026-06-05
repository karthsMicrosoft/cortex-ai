# Cortex iOS Shortcuts Integration

## What this is
Use your iPhone's Action Button (15 Pro Max) or any iOS Shortcut to instantly start a voice recording in the installed Cortex PWA. The Shortcut opens Cortex directly to capture mode, so you can start a voice note without hunting for the app icon.

## Prerequisites
- iPhone running iOS 16.4+ (iOS 17+ recommended for Action Button).
- Cortex PWA already added to the home screen (`Safari` → `Share` → `Add to Home Screen`).
- You've granted Cortex microphone permission at least once.

## One-time setup: build the Shortcut
1. Open the `Shortcuts` app.
2. Tap `+` (top right) to create a new shortcut.
3. Search for `Open URLs` and add it.
4. Paste the URL:

   ```text
   https://gentle-river-06c1e4e10.7.azurestaticapps.net/record?autostart=1
   ```

5. Recommended: tap the action header → toggle `Show in Share Sheet` off, `Use as Quick Action` on.
6. Tap the title at the top (default `Shortcut`) and rename to `Record Cortex Note` (or whatever you like).
7. Pick an icon. Cortex uses indigo `#4F46E5`; a microphone glyph reads well.
8. Tap `Done`.

## Wire the Action Button (iPhone 15 Pro / 15 Pro Max)
1. Go to `Settings` → `Action Button` → `Shortcut`.
2. Tap `Choose a Shortcut` → pick `Record Cortex Note`.
3. Hold the Action Button. Cortex opens in standalone mode and starts recording immediately.

## Wire to Back Tap (any iPhone with iOS 14+)
1. Go to `Settings` → `Accessibility` → `Touch` → `Back Tap` → `Double Tap` (or `Triple Tap`).
2. Scroll down to the `Shortcuts` section → pick `Record Cortex Note`.
3. Double-tap the back of your phone. Recording starts.

## Wire to Control Center (iOS 16+)
1. Go to `Settings` → `Control Center` → add `Shortcuts` if missing.
2. Open Control Center → tap `Shortcuts` → tap `Record Cortex Note`.

## Troubleshooting

### The URL opens in Safari instead of the Cortex app
- Confirm the PWA is installed to the home screen, not just bookmarked.
- iOS sometimes opens the first launch in Safari then "remembers". Open the home-screen Cortex icon once, then trigger the shortcut again.
- On older iOS (<16.4), this is a known limitation; PWAs and shortcuts don't always cooperate. Upgrading iOS resolves it.

### The mic doesn't start automatically
- Open Cortex via the home-screen icon first, allow microphone, and take a quick recording manually so iOS caches the permission grant.
- Re-trigger the shortcut.

### "Permission denied" toast in the app
- iOS Safari/PWA mic permission can reset if you haven't used the app for a while.
- In `Settings` → `Safari` → `Advanced` → `Website Data` → search `cortex` → confirm storage isn't cleared.
- Alternatively, go to `Settings` → `Safari` → `Microphone` → set to `Allow`.

### I want the recording to use a specific note category
- Future enhancement (deferred). Today the deep link always lands in the default capture flow.

## How it works under the hood
The deep link sets `?autostart=1` in the query string. When `CapturePage.tsx` mounts and detects that flag, it calls the same mic-start handler the user normally taps. The manifest's `scope: "/"` means iOS recognizes the URL as belonging to the installed PWA and launches it in standalone mode, with no Safari chrome.

## Privacy
- The Shortcut only opens a URL. No data leaves your device until you record and save.
- All transcription and storage uses your Cortex account on the existing Azure backend.

---
_Round 35 — see PROGRESS.md for context._

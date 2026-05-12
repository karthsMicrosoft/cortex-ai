/**
 * Cortex Clip — popup logic.
 *
 * Vanilla ES module, no bundler. Loaded from popup.html via:
 *   <script type="module" src="popup.js"></script>
 *
 * Stores a clip-scoped JWT in chrome.storage.local. The token can ONLY call
 * POST /api/import/url and POST /api/notes — every other backend route
 * rejects scoped tokens with HTTP 403 (see backend/app/auth/jwt.py).
 */

export const API_BASE =
  "https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io";

const NOT_CONFIGURED_MSG =
  "Not configured — paste a clip token from cortex.app/settings";

export async function getClipToken() {
  const result = await chrome.storage.local.get("clipToken");
  return result?.clipToken || null;
}

export async function setClipToken(token) {
  await chrome.storage.local.set({ clipToken: token });
}

export async function getCurrentTabUrl() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return (tabs && tabs[0] && tabs[0].url) || null;
}

export async function saveCurrentTab() {
  const token = await getClipToken();
  if (!token) {
    throw new Error("Not configured. Paste a clip token first.");
  }
  const url = await getCurrentTabUrl();
  if (!url) {
    throw new Error("No active tab URL.");
  }
  const resp = await fetch(`${API_BASE}/api/import/url`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ url }),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      if (j && j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch (_e) {
      /* ignore JSON parse errors */
    }
    throw new Error(detail);
  }
  return await resp.json();
}

export async function renderState(doc) {
  doc = doc || document;
  const status = doc.getElementById("status");
  const saveBtn = doc.getElementById("saveBtn");
  const token = await getClipToken();
  if (token) {
    if (status) status.textContent = "Ready to save current tab.";
    if (saveBtn) saveBtn.disabled = false;
  } else {
    if (status) status.textContent = NOT_CONFIGURED_MSG;
    if (saveBtn) saveBtn.disabled = true;
  }
}

export async function handleSaveClick(doc) {
  doc = doc || document;
  const status = doc.getElementById("status");
  const saveBtn = doc.getElementById("saveBtn");
  if (saveBtn) saveBtn.disabled = true;
  if (status) status.textContent = "Saving…";
  try {
    await saveCurrentTab();
    if (status) status.textContent = "Saved!";
  } catch (e) {
    if (status) status.textContent = `Error: ${e.message}`;
  } finally {
    // Re-enable button only if token is still present.
    const token = await getClipToken();
    if (saveBtn) saveBtn.disabled = !token;
  }
}

export async function handleSaveTokenClick(doc) {
  doc = doc || document;
  const ta = doc.getElementById("tokenInput");
  const token = ((ta && ta.value) || "").trim();
  if (!token) return;
  await setClipToken(token);
  if (ta) ta.value = "";
  await renderState(doc);
}

// Auto-wire when loaded as a real popup (DOM present and not under vitest).
if (typeof document !== "undefined" && document.getElementById && document.getElementById("saveBtn")) {
  document.addEventListener("DOMContentLoaded", () => {
    renderState();
    const saveBtn = document.getElementById("saveBtn");
    const saveTokenBtn = document.getElementById("saveTokenBtn");
    if (saveBtn) saveBtn.addEventListener("click", () => handleSaveClick());
    if (saveTokenBtn) saveTokenBtn.addEventListener("click", () => handleSaveTokenClick());
  });
}

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installChromeMock, resetChromeMock, setMockTabUrl } from "./chrome-mock.js";

const POPUP_HTML = `
  <div>
    <h1>Cortex Clip</h1>
    <p id="status"></p>
    <button id="saveBtn" disabled>Save</button>
    <details>
      <summary>Set token</summary>
      <textarea id="tokenInput"></textarea>
      <button id="saveTokenBtn">Save token</button>
    </details>
  </div>
`;

let popup;

beforeEach(async () => {
  installChromeMock();
  resetChromeMock();
  document.body.innerHTML = POPUP_HTML;
  // Re-import so module-level state is fresh per test (vi.resetModules then dynamic import)
  vi.resetModules();
  popup = await import("../popup.js");
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("popup state", () => {
  it("shows not-configured state when clipToken is missing", async () => {
    await popup.renderState(document);
    const status = document.getElementById("status").textContent;
    expect(status.toLowerCase()).toContain("not configured");
    expect(document.getElementById("saveBtn").disabled).toBe(true);
  });

  it("shows configured state when clipToken is in storage", async () => {
    await chrome.storage.local.set({ clipToken: "abc.def.ghi" });
    await popup.renderState(document);
    const status = document.getElementById("status").textContent.toLowerCase();
    expect(status).toMatch(/ready|configured/);
    expect(document.getElementById("saveBtn").disabled).toBe(false);
  });
});

describe("save current tab", () => {
  it("POSTs to /api/import/url with the bearer token and tab url", async () => {
    await chrome.storage.local.set({ clipToken: "tok-123" });
    setMockTabUrl("https://news.example.com/story-1");

    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ note_id: "00000000-0000-0000-0000-000000000001" }),
    });

    await popup.handleSaveClick(document);

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, opts] = globalThis.fetch.mock.calls[0];
    expect(url).toContain("/api/import/url");
    expect(opts.method).toBe("POST");
    expect(opts.headers["Authorization"]).toBe("Bearer tok-123");
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opts.body)).toEqual({ url: "https://news.example.com/story-1" });
  });

  it("shows Saved confirmation on successful save", async () => {
    await chrome.storage.local.set({ clipToken: "tok-123" });
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ note_id: "x" }),
    });

    await popup.handleSaveClick(document);
    expect(document.getElementById("status").textContent.toLowerCase()).toContain("saved");
  });

  it("shows error message on failed save", async () => {
    await chrome.storage.local.set({ clipToken: "tok-bad" });
    globalThis.fetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ detail: "scope rejected" }),
    });

    await popup.handleSaveClick(document);
    const status = document.getElementById("status").textContent.toLowerCase();
    expect(status).toContain("error");
    expect(status).toContain("scope rejected");
  });

  it("shows error when no clip token is set", async () => {
    await popup.handleSaveClick(document);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(document.getElementById("status").textContent.toLowerCase()).toContain("error");
  });
});

describe("set token", () => {
  it("persists token to chrome.storage.local and switches to configured state", async () => {
    document.getElementById("tokenInput").value = "  pasted-token-xyz  ";
    await popup.handleSaveTokenClick(document);

    const stored = await chrome.storage.local.get("clipToken");
    expect(stored.clipToken).toBe("pasted-token-xyz");

    expect(document.getElementById("saveBtn").disabled).toBe(false);
  });
});

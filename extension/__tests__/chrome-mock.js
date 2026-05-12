/**
 * Chrome extension API mock for vitest/jsdom tests.
 *
 * Provides a minimal in-memory implementation of:
 *   chrome.storage.local.get / .set
 *   chrome.tabs.query
 *
 * Tests reset state via `resetChromeMock()` and stub `chrome.tabs.query` per test.
 */
const _store = {};
let _currentTabUrl = "https://example.com/article";

export function resetChromeMock() {
  for (const k of Object.keys(_store)) delete _store[k];
  _currentTabUrl = "https://example.com/article";
}

export function setMockTabUrl(url) {
  _currentTabUrl = url;
}

export function installChromeMock() {
  globalThis.chrome = {
    storage: {
      local: {
        get: async (key) => {
          if (typeof key === "string") {
            return key in _store ? { [key]: _store[key] } : {};
          }
          if (Array.isArray(key)) {
            const out = {};
            for (const k of key) if (k in _store) out[k] = _store[k];
            return out;
          }
          // null/undefined → return all
          return { ..._store };
        },
        set: async (obj) => {
          Object.assign(_store, obj);
        },
        remove: async (key) => {
          delete _store[key];
        },
      },
    },
    tabs: {
      query: async () => [{ url: _currentTabUrl, id: 1, active: true }],
    },
  };
}

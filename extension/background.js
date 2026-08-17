// background.js — MV3 service worker
// Responsibilities:
//   1. Hold the auth token (read once from chrome.storage.local)
//   2. Hold the active project slug (set from popup)
//   3. Relay fetch() calls from content scripts — content scripts have
//      host_permissions for 127.0.0.1 but using the service worker as
//      a network gateway avoids any CSP surprises on the LLM sites.
//
// Token storage: chrome.storage.local — never localStorage in page context
// (per §5 of the blueprint).

const DEFAULT_BACKEND = "http://127.0.0.1:8000";

// ── Boot: pull token + active project from storage ───────────────────────
chrome.storage.local.get(
  ["backend_url", "auth_token", "active_project"],
  ({ backend_url, auth_token, active_project }) => {
    if (!backend_url) {
      chrome.storage.local.set({ backend_url: DEFAULT_BACKEND });
    }
    if (!auth_token) {
      console.warn("[sbs] no auth_token set — open the popup to paste it");
    }
    if (!active_project) {
      chrome.storage.local.set({ active_project: null });
    }
  }
);

// ── Message relay ─────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  // msg: { kind: "fetch", path, method, body }
  if (msg && msg.kind === "fetch") {
    fetchFromBackend(msg.path, msg.method || "GET", msg.body)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message || err) }));
    return true; // async response
  }
  if (msg && msg.kind === "get_active_project") {
    chrome.storage.local.get(
      ["active_project", "backend_url", "auth_token"],
      ({ active_project, backend_url, auth_token }) =>
        sendResponse({
          active_project,
          backend_url: backend_url || DEFAULT_BACKEND,
          has_token: Boolean(auth_token),
        })
    );
    return true;
  }
  return false;
});

async function fetchFromBackend(path, method, body) {
  const { backend_url, auth_token } = await chrome.storage.local.get([
    "backend_url",
    "auth_token",
  ]);
  if (!auth_token) {
    throw new Error("auth_token not set — open the extension popup to paste it");
  }
  const base = (backend_url || DEFAULT_BACKEND).replace(/\/+$/, "");
  const r = await fetch(`${base}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${auth_token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`backend ${r.status}: ${txt.slice(0, 240)}`);
  }
  // 202 / 204 might have empty body
  const len = r.headers.get("content-length");
  if (!len || len === "0" || r.status === 204) return null;
  return await r.json();
}

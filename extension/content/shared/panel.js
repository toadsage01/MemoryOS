// content/shared/panel.js
// Injected into every adapter site (claude.ai / gemini.google.com / chatgpt.com).
// Owns: the floating panel UI, brief/capture RPC calls, project state.
// Per-site adapters own only: (a) how to find the input box + insert text,
// (b) how to read the visible transcript DOM.

// The shared panel knows which site it's on by checking window.location
// against the adapter matchers.

const PANEL_ID = "sbs-panel";
const STYLE_ID = "sbs-panel-style";
let panel = null;
let currentAdapter = null;

// ── Site routing ─────────────────────────────────────────────────────────
const ADAPTERS = [
  { host: "claude.ai", api: window.SBS_ADAPTER_CLAUDE },
  { host: "gemini.google.com", api: window.SBS_ADAPTER_GEMINI },
  { host: "chatgpt.com", api: window.SBS_ADAPTER_CHATGPT },
];

function detectAdapter() {
  for (const a of ADAPTERS) {
    if (a.host && window.location.hostname.includes(a.host) && a.api) {
      return a.api;
    }
  }
  return null;
}

// ── Style ────────────────────────────────────────────────────────────────
function injectStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement("style");
  s.id = STYLE_ID;
  s.textContent = `
    #${PANEL_ID} {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 2147483647;
      width: 280px;
      background: #0f172a;
      color: #f1f5f9;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      font-size: 13px;
      border-radius: 10px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
      padding: 12px;
      user-select: none;
    }
    #${PANEL_ID} * {
      box-sizing: border-box;
    }
    #${PANEL_ID} header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 12px;
      font-weight: 600;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    #${PANEL_ID} .sbs-title {
      font-size: 13px;
      color: #f1f5f9;
      font-weight: 700;
      text-transform: none;
      letter-spacing: 0;
    }
    #${PANEL_ID} .sbs-draghandle {
      cursor: grab;
      padding: 4px 8px;
      color: #475569;
    }
    #${PANEL_ID} .sbs-draghandle:active { cursor: grabbing; }
    #${PANEL_ID} select, #${PANEL_ID} button {
      width: 100%;
      padding: 7px 10px;
      background: #1e293b;
      border: 1px solid #334155;
      color: #f1f5f9;
      border-radius: 6px;
      font-size: 13px;
      font-family: inherit;
      margin-bottom: 6px;
      cursor: pointer;
    }
    #${PANEL_ID} button {
      background: #0c4a6e;
      border-color: #38bdf8;
      font-weight: 500;
      transition: background 0.15s;
    }
    #${PANEL_ID} button:hover { background: #075985; }
    #${PANEL_ID} button.sbs-capture {
      background: #4c1d95;
      border-color: #8b5cf6;
    }
    #${PANEL_ID} button.sbs-capture:hover { background: #5b21b6; }
    #${PANEL_ID} .sbs-status {
      font-size: 11px;
      color: #94a3b8;
      margin: 6px 0;
      min-height: 16px;
      word-break: break-word;
    }
    #${PANEL_ID} .sbs-status.error { color: #fca5a5; }
    #${PANEL_ID} .sbs-status.ok { color: #86efac; }
    #${PANEL_ID} .sbs-toggle {
      position: absolute;
      top: 6px;
      right: 8px;
      background: transparent;
      border: none;
      color: #475569;
      font-size: 14px;
      cursor: pointer;
      padding: 2px 6px;
      margin: 0;
    }
    #${PANEL_ID}.sbs-collapsed .sbs-body { display: none; }
    #${PANEL_ID}.sbs-collapsed { width: 160px; }
  `;
  document.documentElement.appendChild(s);
}

// ── Panel render ────────────────────────────────────────────────────────
async function renderPanel() {
  if (document.getElementById(PANEL_ID)) return panel;
  injectStyle();
  panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.innerHTML = `
    <button class="sbs-toggle" title="collapse">–</button>
    <header>
      <span class="sbs-title">Second Brain</span>
    </header>
    <div class="sbs-body">
      <select class="sbs-project" id="sbs-project-select">
        <option>loading…</option>
      </select>
      <button class="sbs-brief">brief me</button>
      <button class="sbs-capture">capture</button>
      <div class="sbs-status"></div>
    </div>
  `;
  document.documentElement.appendChild(panel);

  // Collapse / expand
  panel.querySelector(".sbs-toggle").addEventListener("click", () => {
    panel.classList.toggle("sbs-collapsed");
    panel.querySelector(".sbs-toggle").textContent = panel.classList.contains("sbs-collapsed") ? "+" : "–";
  });

  // Drag handle (the whole header)
  const header = panel.querySelector("header");
  makeDraggable(panel, header);

  // Wire buttons
  panel.querySelector(".sbs-brief").addEventListener("click", onBriefClick);
  panel.querySelector(".sbs-capture").addEventListener("click", onCaptureClick);

  // Load projects
  await refreshProjects();
  return panel;
}

function makeDraggable(el, handle) {
  let dragging = false;
  let offsetX = 0;
  let offsetY = 0;
  handle.addEventListener("mousedown", (e) => {
    dragging = true;
    const rect = el.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    el.style.left = `${e.clientX - offsetX}px`;
    el.style.top = `${e.clientY - offsetY}px`;
    el.style.right = "auto";
    el.style.bottom = "auto";
  });
  document.addEventListener("mouseup", () => {
    dragging = false;
  });
}

// ── State + RPC ──────────────────────────────────────────────────────────
async function rpc(kind, path, method, body) {
  return new Promise((resolve) =>
    chrome.runtime.sendMessage({ kind, path, method, body }, resolve)
  );
}

async function refreshProjects() {
  const select = panel.querySelector("#sbs-project-select");
  const r = await rpc("fetch", "/projects", "GET");
  if (!r.ok) {
    select.innerHTML = `<option>${r.error || "failed"}</option>`;
    return;
  }
  const projects = r.data || [];
  if (!projects.length) {
    select.innerHTML = `<option value="">(no projects yet — create one)</option>`;
    return;
  }
  select.innerHTML = projects
    .map((p) => `<option value="${p.slug}">${p.name} (${p.slug})</option>`)
    .join("");
  // Restore active project
  const { active_project } = await chrome.storage.local.get(["active_project"]);
  if (active_project) {
    select.value = active_project;
  }
  select.addEventListener("change", async () => {
    if (select.value) {
      await chrome.storage.local.set({ active_project: select.value });
      setStatus(`project: ${select.value}`, "ok");
    }
  });
}

async function getActiveProject() {
  const { active_project } = await chrome.storage.local.get(["active_project"]);
  if (!active_project) {
    throw new Error("no active project — pick one in the panel");
  }
  return active_project;
}

// ── Brief me: pull brief from backend, insert into input box (no autosend) ─
async function onBriefClick() {
  setStatus("fetching brief…");
  try {
    const project = await getActiveProject();
    // Optional: pass last few turns as recent_turns for better retrieval
    let recentTurns = null;
    if (currentAdapter && currentAdapter.readRecentTurns) {
      try {
        recentTurns = currentAdapter.readRecentTurns();
      } catch (e) {
        // not a hard failure — fall back to project-state-only retrieval
        console.warn("[sbs] readRecentTurns failed:", e);
      }
    }
    const r = await rpc("fetch", "/context/brief", "POST", {
      project_slug: project,
      recent_turns: recentTurns,
    });
    if (!r.ok) throw new Error(r.error);
    const brief = r.data.brief;
    if (!currentAdapter || !currentAdapter.insertIntoInput) {
      throw new Error("no adapter.insertIntoInput for this site");
    }
    const ok = currentAdapter.insertIntoInput(brief + "\n\n----\n\n");
    if (!ok) throw new Error("could not find input box — try opening a new chat");
    setStatus(`brief inserted (${r.data.word_count} words) — review + send`);
  } catch (err) {
    setStatus(String(err.message || err), "error");
  }
}

// ── Capture: read transcript DOM, send to /ingest ─────────────────────────
async function onCaptureClick() {
  setStatus("capturing…");
  try {
    const project = await getActiveProject();
    if (!currentAdapter || !currentAdapter.readTranscript) {
      throw new Error("no adapter.readTranscript for this site");
    }
    const { transcript, model, url } = currentAdapter.readTranscript();
    if (!transcript || !transcript.trim()) {
      throw new Error("no transcript found — is the chat empty?");
    }
    const r = await rpc("fetch", "/ingest", "POST", {
      project_slug: project,
      transcript,
      site: window.location.hostname,
      url: url || window.location.href,
      model: model || null,
    });
    if (!r.ok) throw new Error(r.error);
    setStatus(`captured (${transcript.length} chars) — conv ${r.data.conversation_id.slice(0, 8)}`, "ok");
  } catch (err) {
    setStatus(String(err.message || err), "error");
  }
}

function setStatus(msg, cls = "") {
  const el = panel.querySelector(".sbs-status");
  el.textContent = msg;
  el.className = "sbs-status" + (cls ? " " + cls : "");
}

// ── Boot ─────────────────────────────────────────────────────────────────
function boot() {
  currentAdapter = detectAdapter();
  if (!currentAdapter) {
    // Not on a known site — silently do nothing.
    return;
  }
  // The DOM might not be ready yet on these SPA sites. Wait for the
  // first user gesture (e.g. clicking the extension icon opens the popup,
  // but the panel is always injected by the content script). Render once
  // and re-render if needed.
  renderWhenReady();
}

function renderWhenReady() {
  // Try rendering every second for up to 30 seconds — Claude / ChatGPT are
  // SPAs that can take a few seconds to mount their root div.
  let attempts = 0;
  const maxAttempts = 30;
  const t = setInterval(() => {
    attempts++;
    if (document.body) {
      clearInterval(t);
      renderPanel();
      return;
    }
    if (attempts >= maxAttempts) {
      clearInterval(t);
      console.warn("[sbs] gave up waiting for body after 30s");
    }
  }, 1000);
}

boot();

// popup.js — popup script (runs when user clicks the extension icon)
// Two states:
//   - "setup" if no auth_token: prompt user to paste it
//   - "controls" if token is present: pick active project, open an LLM tab

const statusEl = document.getElementById("status");
const setupEl = document.getElementById("setup");
const controlsEl = document.getElementById("controls");
const tokenInput = document.getElementById("token-input");
const backendInput = document.getElementById("backend-input");
const saveBtn = document.getElementById("save-btn");
const projectSelect = document.getElementById("project-select");
const refreshBtn = document.getElementById("refresh-projects");
const openTabBtn = document.getElementById("open-tab");

// ── On open ─────────────────────────────────────────────────────────────
chrome.storage.local.get(
  ["backend_url", "auth_token", "active_project"],
  async ({ backend_url, auth_token, active_project }) => {
    backendInput.value = backend_url || "http://127.0.0.1:8000";
    if (auth_token) {
      await showControls();
    } else {
      showSetup();
    }
  }
);

function showSetup() {
  setupEl.hidden = false;
  controlsEl.hidden = true;
  statusEl.textContent = "needs token";
  statusEl.style.color = "var(--err)";
}

async function showControls() {
  setupEl.hidden = true;
  controlsEl.hidden = false;
  statusEl.textContent = "ready";
  statusEl.style.color = "var(--ok)";
  await refreshProjects();
}

async function refreshProjects() {
  projectSelect.innerHTML = "";
  try {
    const r = await sendToBackground({
      kind: "fetch",
      path: "/projects",
      method: "GET",
    });
    if (!r.ok) throw new Error(r.error);
    const projects = r.data || [];
    if (!projects.length) {
      const opt = document.createElement("option");
      opt.textContent = "(no projects yet)";
      opt.value = "";
      projectSelect.appendChild(opt);
      return;
    }
    const { active_project } = await chrome.storage.local.get(["active_project"]);
    for (const p of projects) {
      const opt = document.createElement("option");
      opt.value = p.slug;
      opt.textContent = `${p.name} (${p.slug})`;
      if (p.slug === active_project) opt.selected = true;
      projectSelect.appendChild(opt);
    }
  } catch (err) {
    const opt = document.createElement("option");
    opt.textContent = "couldn't load projects — backend down?";
    opt.value = "";
    projectSelect.appendChild(opt);
    statusEl.textContent = "backend down?";
    statusEl.style.color = "var(--err)";
  }
}

// ── Save token + backend URL ────────────────────────────────────────────
saveBtn.addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  const backend = backendInput.value.trim() || "http://127.0.0.1:8000";
  if (!token) {
    tokenInput.focus();
    return;
  }
  await chrome.storage.local.set({ auth_token: token, backend_url: backend });
  // Verify by hitting /whoami
  const r = await sendToBackground({ kind: "fetch", path: "/whoami", method: "GET" });
  if (r.ok && r.data && r.data.ok) {
    await showControls();
  } else {
    statusEl.textContent = "token rejected";
    statusEl.style.color = "var(--err)";
  }
});

// ── Project select → write active_project ───────────────────────────────
projectSelect.addEventListener("change", async () => {
  const slug = projectSelect.value;
  if (!slug) return;
  await chrome.storage.local.set({ active_project: slug });
  statusEl.textContent = `project: ${slug}`;
});

refreshBtn.addEventListener("click", refreshProjects);

// ── Open Claude tab ─────────────────────────────────────────────────────
openTabBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: "https://claude.ai/" });
  window.close();
});

// ── Helpers ──────────────────────────────────────────────────────────────
function sendToBackground(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

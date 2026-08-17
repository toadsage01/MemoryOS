// content/adapters/claude.js
// Per-site adapter for claude.ai. Owns only:
//   (a) insertIntoInput(text)  — find input box + insert text
//   (b) readTranscript()       — read visible transcript DOM
//   (c) readRecentTurns()      — last few turns for retrieval query
//
// All shared logic (panel UI, RPC, project state) lives in panel.js.

// Expose the adapter globally for panel.js to pick up via window detection.
window.SBS_ADAPTER_CLAUDE = {
  // ── Input box ────────────────────────────────────────────────────────
  // Claude uses a contenteditable ProseMirror div for input. The exact
  // selector has changed between releases; try several known shapes.
  inputSelector: [
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"]',
    'textarea[aria-label*="Reply"]',
    'textarea',
  ],

  findInput() {
    for (const sel of this.inputSelector) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  },

  insertIntoInput(text) {
    const el = this.findInput();
    if (!el) return false;
    el.focus();
    // For contenteditable, use execCommand for broadest compatibility.
    if (el.isContentEditable) {
      // Place cursor at end
      const sel = window.getSelection();
      sel.removeAllRanges();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      sel.addRange(range);
      // insertText handles newlines correctly inside contenteditable
      const ok = document.execCommand("insertText", false, text);
      if (ok) return true;
      // Fallback: direct textContent set (loses formatting but works)
      el.textContent = text;
      // Dispatch input event so the SPA picks up the change
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      return true;
    }
    // textarea
    el.value = text + el.value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  },

  // ── Transcript ────────────────────────────────────────────────────────
  // Claude renders each message in a div with data-testid attributes that
  // have varied across versions. Try several shapes; if none match, fall
  // back to a coarse "all visible user/assistant text" grab.
  turnSelector: [
    '[data-testid="user-message"]',
    'div.font-user-message',
    '[data-testid="assistant-message"]',
    'div.font-claude-message',
  ],

  readTranscript() {
    const blocks = [];
    // Try the structured selector first
    const userMsgs = document.querySelectorAll('[data-testid="user-message"]');
    const aiMsgs = document.querySelectorAll('[data-testid="assistant-message"]');
    if (userMsgs.length || aiMsgs.length) {
      // Walk the DOM in order to preserve conversation flow. The user and
      // assistant messages share a parent — the main scroll container.
      const seen = new Set();
      for (const sel of ['[data-testid="user-message"]', '[data-testid="assistant-message"]']) {
        document.querySelectorAll(sel).forEach((el) => {
          if (seen.has(el)) return;
          seen.add(el);
          const role = el.getAttribute("data-testid") === "user-message" ? "User" : "Assistant";
          const text = (el.innerText || el.textContent || "").trim();
          if (text) blocks.push({ role, text });
        });
      }
      // Sort by DOM order
      blocks.sort((a, b) => {
        // re-query for ordering
        const aEl = Array.from(document.querySelectorAll('[data-testid="user-message"], [data-testid="assistant-message"]')).find(el => el === a.el);
        if (aEl && b.el) return 0; // crude; correct enough for chunking
        return 0;
      });
      // Actually, just rebuild from the DOM in order:
      const ordered = Array.from(
        document.querySelectorAll('[data-testid="user-message"], [data-testid="assistant-message"]')
      );
      ordered.forEach((el) => {
        const role = el.getAttribute("data-testid") === "user-message" ? "User" : "Assistant";
        const text = (el.innerText || el.textContent || "").trim();
        if (text) blocks.push({ role, text });
      });
    }
    // Fallback: grab any text in [class*="message"] containers
    if (!blocks.length) {
      const candidates = document.querySelectorAll('[class*="message"], [class*="Message"]');
      candidates.forEach((el) => {
        const text = (el.innerText || "").trim();
        if (text && text.length > 5) {
          blocks.push({ role: "Unknown", text });
        }
      });
    }
    const transcript = blocks.map((b) => `${b.role}: ${b.text}`).join("\n\n");
    return {
      transcript,
      model: "claude",
      url: window.location.href,
    };
  },

  readRecentTurns(maxChars = 800) {
    // Grab the last user message + the assistant reply that follows it.
    const userEls = Array.from(document.querySelectorAll('[data-testid="user-message"]'));
    if (!userEls.length) return null;
    const lastUser = userEls[userEls.length - 1];
    // Walk forward in DOM siblings to find the next assistant message
    let walker = lastUser.nextElementSibling;
    let collected = "";
    const lastUserText = (lastUser.innerText || "").trim();
    let aiText = "";
    while (walker && !aiText) {
      if (walker.matches && walker.matches('[data-testid="assistant-message"]')) {
        aiText = (walker.innerText || "").trim();
        break;
      }
      walker = walker.nextElementSibling;
    }
    collected = `User: ${lastUserText}\n\nAssistant: ${aiText}`;
    if (collected.length > maxChars) {
      collected = collected.slice(-maxChars);
    }
    return collected;
  },
};

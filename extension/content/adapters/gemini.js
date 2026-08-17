// content/adapters/gemini.js
// Per-site adapter for gemini.google.com.

window.SBS_ADAPTER_GEMINI = {
  inputSelector: [
    'rich-text-area [contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"]',
    'div.ql-editor[contenteditable="true"]',
    'rich-textarea div[contenteditable="true"]',
    'div[contenteditable="true"]',
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
    if (el.isContentEditable) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      sel.addRange(range);
      const ok = document.execCommand("insertText", false, text);
      if (ok) return true;
      el.textContent = text + el.textContent;
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      return true;
    }
    el.value = text + el.value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  },

  readTranscript() {
    // Gemini's DOM uses <message-content> custom elements + standard divs
    // with class names like "model-response-text", "query-text".
    // We try the structured path first, fall back to coarse.
    const blocks = [];
    const queries = document.querySelectorAll(
      '.query-text, message-content[model], [data-test-id="user-query"]'
    );
    const replies = document.querySelectorAll(
      '.model-response-text, message-content[user], [data-test-id="model-response"]'
    );
    // Simpler approach: grab everything under the main conversation container
    // in DOM order, classifying each block as User or Assistant based on
    // parent class hints.
    const allMsgs = Array.from(
      document.querySelectorAll(
        'message-content, .query-text, .model-response-text, .conversation-container > div'
      )
    );
    for (const el of allMsgs) {
      const text = (el.innerText || el.textContent || "").trim();
      if (!text || text.length < 2) continue;
      const parent = el.closest
        ? el.closest('[class*="query"], [class*="user"], [class*="model"], message-content[model]')
        : null;
      const roleHint = parent
        ? (parent.getAttribute("model") !== null
          ? "Assistant"
          : parent.getAttribute("user") !== null
          ? "User"
          : "Unknown")
        : "Unknown";
      blocks.push({ role: roleHint, text });
    }
    const transcript = blocks.map((b) => `${b.role}: ${b.text}`).join("\n\n");
    return { transcript, model: "gemini", url: window.location.href };
  },

  readRecentTurns(maxChars = 800) {
    const { transcript } = this.readTranscript();
    if (!transcript) return null;
    return transcript.slice(-maxChars);
  },
};

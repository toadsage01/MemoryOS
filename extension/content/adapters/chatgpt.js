// content/adapters/chatgpt.js
// Per-site adapter for chatgpt.com.

window.SBS_ADAPTER_CHATGPT = {
  inputSelector: [
    'div#prompt-textarea[contenteditable="true"]',
    'div[contenteditable="true"][data-virtualkeyboard="true"]',
    'textarea[data-id="root"]',
    'div[contenteditable="true"][role="textbox"]',
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
      range.collapse(false);  // collapse to end
      sel.addRange(range);
      const ok = document.execCommand("insertText", false, text);
      if (ok) return true;
      // execCommand is deprecated in some Chrome channels; use direct
      // TextNode insertion as a final fallback.
      el.textContent = text + el.textContent;
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      return true;
    }
    el.value = text + el.value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  },

  readTranscript() {
    // ChatGPT labels messages with data-message-author-role="user" or
    // "assistant" inside an [data-testid^="conversation-turn-"] container.
    const turns = Array.from(
      document.querySelectorAll('[data-testid^="conversation-turn-"]')
    );
    if (!turns.length) {
      // Fallback: grab any [data-message-author-role] elements in order
      const roles = Array.from(
        document.querySelectorAll('[data-message-author-role]')
      );
      const blocks = roles.map((el) => {
        const role = el.getAttribute("data-message-author-role") || "unknown";
        const text = (el.innerText || "").trim();
        return {
          role: role.charAt(0).toUpperCase() + role.slice(1),
          text,
        };
      }).filter((b) => b.text);
      const transcript = blocks.map((b) => `${b.role}: ${b.text}`).join("\n\n");
      return { transcript, model: "chatgpt", url: window.location.href };
    }
    // Structured path
    const blocks = turns.map((el) => {
      const roleEl = el.querySelector('[data-message-author-role]');
      const role = roleEl?.getAttribute("data-message-author-role") || "unknown";
      const text = (el.innerText || "").trim();
      return {
        role: role.charAt(0).toUpperCase() + role.slice(1),
        text,
      };
    }).filter((b) => b.text);
    const transcript = blocks.map((b) => `${b.role}: ${b.text}`).join("\n\n");
    return { transcript, model: "chatgpt", url: window.location.href };
  },

  readRecentTurns(maxChars = 800) {
    const { transcript } = this.readTranscript();
    if (!transcript) return null;
    return transcript.slice(-maxChars);
  },
};

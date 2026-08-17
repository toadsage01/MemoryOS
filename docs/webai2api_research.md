# WebAI2API research — patterns applicable to Second Brain Sync

Source: [github.com/foxhui/WebAI2API](https://github.com/foxhui/WebAI2API)
Tag at time of research: main branch, v3.0.0, ~1250 stars.
Architecture: Node.js + Playwright + Camoufox (anti-detection Firefox fork) →
exposes an OpenAI-compatible HTTP API on top of LMArena / Gemini /
ChatGPT / DeepSeek web UIs.

## What WebAI2API is

It's a **server-side browser automation bridge**. You run it on a machine
(or in Docker), it spins up browser instances logged into the various AI
websites, and exposes `POST /v1/chat/completions` that downstream tools
(curl, libs, your code) can hit like a normal OpenAI endpoint. The
"chat" is actually the browser typing into the website and reading the
response back.

Multi-window concurrency + per-instance cookie/profile isolation lets one
deployment serve multiple accounts in parallel.

## How this differs from Second Brain Sync

**Fundamentally different layer of the stack.**

| Aspect | WebAI2API | Second Brain Sync |
|---|---|---|
| Layer | Server-side browser automation | User-side browser extension |
| Who chats with the LLM | WebAI2API's Camoufox instance, on your behalf | You, in your own browser tab |
| Where auth lives | Server config file (`auth: sk-...`) | Local `.env` (auto-minted token) |
| Browser | Headless Camoufox on a server | Your real, daily-driver Chrome |
| Goal | Expose LLM as an API | Give the LLM you're already chatting with persistent memory |
| Concurrency model | Multi-window, multi-account | Single user, single browser |
| Failure mode | Auto-restart supervisor + retry queue | Fail loudly, log + show in panel |

So the **architecture as a whole does not transfer**. But the project
contains several **individual patterns worth lifting** — and several
that look attractive but are explicitly wrong for SBS's scale.

## Patterns worth lifting (v1.1 candidates)

### 1. SSE heartbeat keepalive for long operations

**Where**: WebAI2API's `src/server/respond.js` (5KB) — sends
`:keepalive` SSE comments during long LLM responses so the client's
HTTP timeout never fires. Two modes: comment-mode (default, SSE-standard)
and content-mode (for clients that need JSON data to reset their timer).

**Why it applies to SBS**: `/context/brief` makes a synchronous curator
call to Gemini Flash. On a cold start or with a complex prompt, this can
take 5-15 seconds. The browser `fetch()` in `panel.js` shows nothing
during that window — the user can't tell if it's working or hung.

**How to lift it**: convert `/context/brief` to an SSE endpoint. Send
a `:thinking` comment every 1s while the curator call is in flight,
then a single `data:` event with the brief text. The panel's status
line stays "still working…" instead of looking dead.

This is the single highest-value pattern to lift from WebAI2API.

### 2. Adapter registry pattern

**Where**: `src/backend/registry.js` (10KB) — a registry of named
adapters (LMArena, Gemini, ChatGPT, ...) with metadata about supported
features (text gen, image gen, video gen).

**Why it applies**: SBS already has the adapter pattern (claude.js /
gemini.js / chatgpt.js) but no registry — `panel.js` hardcodes the
host→adapter mapping in `ADAPTERS`. As adapters grow, the registry
pattern keeps that mapping data-driven.

**How to lift it**: each adapter declares a static `host_patterns`
array and a `capabilities` object. `panel.js` iterates a list of
adapters instead of a hardcoded switch. Pure refactor — no behavior
change — but makes adding the 4th + 5th site trivial.

### 3. Config validator with explicit error messages

**Where**: `src/config/validator.js` (11KB) — checks the YAML config
at startup, returns human-readable errors like "port must be 1-65535,
got 'abc'".

**Why it applies**: SBS uses pydantic-settings, which already does
type validation but its error messages are sometimes cryptic. A thin
"explain-like-I'm-5" wrapper on top would help the user understand
what's wrong when `.env` has a typo.

**How to lift it**: a `validate_config()` function called from
`lifespan()` in `main.py` that walks the loaded `Settings` and raises
a `ConfigError` with a list of human-readable problems. Lower priority
than the SSE pattern — current pydantic errors are usable, just not
great.

## Patterns explicitly NOT applicable (and why)

### 1. Process supervisor with auto-restart

**Where**: `supervisor.js` (428 lines) — watchdog that spawns
`src/server/server.js` as a child process, auto-restarts on crash
(except for `FATAL_EXIT_CODES`), and accepts IPC commands like
`RESTART`, `STOP`, `GET_VNC_INFO`.

**Why not for SBS**: blueprint §1.3 says "no need for horizontal
scaling, no need for a message queue ... start with FastAPI
`BackgroundTasks`". `uvicorn --reload` is the dev supervisor; in prod,
`systemd` or `pm2` are the right primitives. A bespoke Node-style
watchdog is the wrong layer for a Python single-user service.

### 2. Multi-window concurrency + account isolation

**Where**: `src/backend/pool/` — manages multiple Camoufox instances
each with their own cookies + proxy.

**Why not for SBS**: SBS is single-user by design (blueprint §0: "This
is not an enterprise product. It is not multi-tenant. It has exactly
one user"). One browser, one extension, one user. Adding multi-account
would violate §9 (explicit non-goals: "Multi-user auth, accounts, or
permissions").

### 3. Anti-detection / Camoufox / headless mode

**Where**: WebAI2API migrated from Puppeteer to Camoufox specifically
to evade bot detection (per their README's "Historical Version Note").

**Why not for SBS**: SBS doesn't automate the LLM sites at all —
the user types into the LLM site themselves, and the extension only
reads the visible DOM + inserts text into the input box (exactly what
the user would have typed). No detection surface to evade.

### 4. WebUI for management

**Where**: `webui/` directory — a visual management interface with
real-time logs, VNC, adapter management.

**Why not for SBS**: blueprint §9: "Any UI beyond the extension panel
+ popup (no separate web dashboard for v1 — that's a later
Kairos-integration concern, not this build)". Explicit non-goal.

### 5. Task queue with backpressure

**Where**: `src/server/queue.js` (12KB) — task queue that rejects
non-streaming requests when the backlog exceeds a threshold.

**Why not for SBS**: at solo-user throughput (one user, one capture
at a time, ~6 messages per auto-capture cycle), there is no backlog.
FastAPI's `BackgroundTasks` is enough (blueprint §1.3). Adding a
queue would be speculative engineering.

### 6. Streaming response shape (`/v1/chat/completions` style)

**Where**: WebAI2API streams tokens back as the LLM produces them
in the headless browser.

**Why not for SBS**: SBS doesn't proxy LLM responses. The curator
model returns a single brief text in one shot — there's no token-by-
token stream to relay. (The SSE heartbeat pattern above is the only
piece of streaming that makes sense for SBS, and it's about keeping
the connection alive, not streaming content.)

## What I would NOT copy from WebAI2API

- **Config in YAML**: their `config.example.yaml` (9KB) is well-
  documented, but `.env` + pydantic-settings is the Python-ecosystem
  standard and SBS already uses it. Switching would be churn for no
  real benefit at this scale.
- **Camoufox dependency**: not needed, see above.
- **Inquirer prompts for interactive setup** (`@inquirer/prompts`):
  WebAI2API uses these for first-run setup. SBS uses the extension
  popup for the same flow, which is more appropriate for a browser-
  extension-based product.

## Concrete next-step recommendations for SBS v1.1

If you want to apply the research, the priorities in order:

1. **SSE heartbeat for `/context/brief`** — biggest UX win. ~30 lines
   of Python (switch the route to `StreamingResponse`, yield
   `: keepalive\n\n` in a loop while waiting on the curator call).
   ~10 lines of JS in `panel.js` to consume the stream.
2. **Adapter registry refactor** — makes adding the 4th site trivial.
   Pure code reorganization, no behavior change.
3. **Config validator wrapper** — nicer error messages. Low priority.

None of these are blocking. The current code works; these are
polish items for after you've run it against real captures and
have a clearer sense of what hurts.

# Second Brain Sync

A personal, single-user system that gives every LLM you talk to — through
their normal web chat UIs (Claude, Gemini, ChatGPT) — access to the same
persistent project memory, so you never retype context, never manually
remind a model what you're doing, and never redo research you already did
weeks ago and can't locate.

This is **not** an enterprise product. It is **not** multi-tenant. It has
exactly one user. It is built at that scale on purpose.

## What it is

- A **FastAPI backend** running locally (localhost only, token-authenticated)
  that stores conversations, projects, decisions, goals, and research notes
  in a knowledge graph (Neo4j) plus a hybrid retrieval layer (ChromaDB for
  dense vectors + BM25 for sparse keyword matching).
- A **Manifest V3 browser extension** that adds a small floating panel to
  your Claude / Gemini / ChatGPT tabs. Two buttons: **Brief me** (paste a
  short context block into the input box — you still review and press enter)
  and **Capture** (send the current transcript to the backend for ingestion).

The backend never talks to any LLM provider's API on your behalf for the
chat itself. You still type into the web UI as normal. The backend's own
free-tier API calls are only for embedding text and writing the short
"brief" — not for having the actual conversation.

## Architecture

```
Browser (you)  ─── extension panel ───  FastAPI backend (localhost)
                                          │
                                  ┌───────┼───────┐
                                  ▼       ▼       ▼
                              Neo4j   ChromaDB   BM25
                              (graph)  (dense)   (sparse)
```

Three moving parts: backend (memory + retrieval + curation), extension
(the only thing that touches any LLM's web UI), and stores (graph + vector
+ keyword, queried together via reciprocal rank fusion).

## Status (per §7 build order)

| Phase | What | Status |
|---|---|---|
| 0 | Scaffold, .env.example, .gitignore, docker-compose for Neo4j | done |
| 1 | Graph schema, `/ingest` end-to-end with manual test | done (code-complete) |
| 2 | Hybrid retrieval, `/context/brief`, `/dedup-check` | done (code-complete) |
| 3 | Extension MVP on claude.ai | done |
| 4 | Gemini + ChatGPT adapters | done |
| 5 | Debounced auto-capture, threshold notes, README | done |

**"Code-complete"** means the code is written and importable, but I have
not been able to exercise the full end-to-end flow against a live Neo4j +
real Gemini keys in this environment. The manual test transcripts in
`backend/tests/fixtures/` are clearly labeled as such — never in the
running system.

## Quick start

```bash
# 1. Clone and configure
git clone https://github.com/toadsage01/second-brain-sync.git
cd second-brain-sync
cp .env.example .env
# edit .env: set NEO4J_PASSWORD, EMBEDDING_API_KEY, CURATOR_API_KEY

# 2. Start Neo4j (Community edition, free, persisted volume)
docker compose up -d neo4j
# wait for http://localhost:7474 to respond

# 3. Install backend deps + run
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 4. Load the extension
# Chrome: chrome://extensions → enable Developer mode → Load unpacked
# → select the extension/ folder
# → click the extension icon, paste the LOCAL_AUTH_TOKEN from .env

# 5. Use it
# Open a new Claude/Gemini/ChatGPT tab, click the floating panel,
# pick a project, hit Brief me or Capture.
```

## Manual test flow (no extension required)

```bash
# After step 3 above, the backend is on :8000. With the token from .env:
TOKEN=$(grep LOCAL_AUTH_TOKEN .env | cut -d= -f2)

# Create a project
curl -s -X POST http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Test project", "slug": "test"}'

# Ingest a test transcript
curl -s -X POST http://127.0.0.1:8000/ingest \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"project_slug": "test", "site": "claude.ai", "transcript": "..."}'

# Get a brief
curl -s -X POST http://127.0.0.1:8000/context/brief \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"project_slug": "test"}'

# Dedup-check a candidate question
curl -s -X POST http://127.0.0.1:8000/dedup-check \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"project_slug": "test", "candidate": "Should I use Celery for this?"}'
```

## Non-goals (§9 of blueprint)

- Multi-user auth, accounts, permissions.
- Cloud hosting / deployment automation (local-only by default).
- Any UI beyond the extension panel + popup.
- Automatic project classification.
- Support for any site not in `SITE_ADAPTERS_V1`.

## Repository layout

See the blueprint §3. The high-level layout:

```
second-brain-sync/
├── .env.example
├── .gitignore
├── docker-compose.yml          # Neo4j only
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py             # FastAPI app
│       ├── config.py           # pydantic settings
│       ├── auth.py             # local bearer token
│       ├── graph/              # Neo4j schema + client
│       ├── retrieval/          # embed + dense + sparse + hybrid
│       ├── ingest/             # chunker + pipeline
│       ├── curator/            # brief + dedup
│       └── routers/            # context / ingest / dedup / projects
├── extension/
│   ├── manifest.json
│   ├── background.js
│   ├── popup/
│   ├── content/
│   │   ├── shared/panel.js
│   │   └── adapters/           # claude / gemini / chatgpt
│   └── icons/
└── README.md
```

## License

MIT — see `LICENSE` (or rely on `pyproject.toml` until the file lands).

"""Neo4j schema for Second Brain Sync (§4.1 of the blueprint).

Keep this small. Do not add speculative node types.

Nodes:
    (:Project {name, slug, created_at, status})
    (:Goal {text, created_at, active})
    (:Decision {text, created_at})
    (:ResearchNote {summary, source, created_at, chunk_ref})
    (:Conversation {model, url_or_site, captured_at})
    (:Entity {name, type})

Edges:
    (:Project)-[:HAS_GOAL]->(:Goal)
    (:Project)-[:HAS_DECISION]->(:Decision)
    (:Project)-[:HAS_RESEARCH]->(:ResearchNote)
    (:ResearchNote)-[:FROM]->(:Conversation)
    (:*)-[:MENTIONS]->(:Entity)

The schema is applied on boot via `ensure_schema()` — Neo4j is mostly
schema-less, but we still create the constraints up front so lookups on
slug / chunk_ref stay fast and dedup-safe.
"""
from __future__ import annotations

# ── Constraint statements (idempotent — safe to run on every boot) ────────
CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT project_slug IF NOT EXISTS "
    "FOR (p:Project) REQUIRE p.slug IS UNIQUE",
    "CREATE CONSTRAINT goal_id IF NOT EXISTS "
    "FOR (g:Goal) REQUIRE g.id IS UNIQUE",
    "CREATE CONSTRAINT decision_id IF NOT EXISTS "
    "FOR (d:Decision) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT research_note_id IF NOT EXISTS "
    "FOR (r:ResearchNote) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT conversation_id IF NOT EXISTS "
    "FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT entity_unique IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE",
]

# ── Indexes for retrieval hot paths ──────────────────────────────────────
INDEXES: list[str] = [
    "CREATE INDEX project_status IF NOT EXISTS "
    "FOR (p:Project) ON (p.status)",
    "CREATE INDEX goal_active IF NOT EXISTS "
    "FOR (g:Goal) ON (g.active)",
    "CREATE INDEX research_note_created IF NOT EXISTS "
    "FOR (r:ResearchNote) ON (r.created_at)",
]


def all_statements() -> list[str]:
    """All schema statements in apply-once order."""
    return [*CONSTRAINTS, *INDEXES]

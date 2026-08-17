"""Ingest pipeline (§4.2 of the blueprint).

Flow:
1. extension POSTs raw transcript + project tag
2. chunk
3. embed each chunk → ChromaDB
4. single call to curator to extract {decisions, goals_mentioned, entities}
   (structured-output prompt; fail loudly on parse error)
5. write graph nodes/edges
6. add chunk text to BM25 index

Steps 2-6 run as a BackgroundTask so /ingest returns immediately.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from .. import graph
from ..retrieval import dense, sparse
from .chunker import chunk_transcript

log = logging.getLogger(__name__)


def run_ingest(
    project_slug: str,
    transcript: str,
    site: str,
    url: str | None = None,
    model: str | None = None,
    conv_id: str | None = None,
) -> str:
    """End-to-end ingest. Returns the conversation_id.

    If `conv_id` is None (default), one is minted here. Callers that want
    to know the id before the pipeline runs (e.g. the /ingest router,
    which echoes it back to the extension immediately) can pass one in.
    """
    if conv_id is None:
        conv_id = str(uuid.uuid4())
    captured_at = datetime.now(timezone.utc).isoformat()

    # 1. Create / fetch the project (defensive — should already exist)
    project = _ensure_project(project_slug)
    project_id = project["id"]

    # 2. Create the Conversation node first so chunks can back-reference it
    graph.run_write(
        """
        MATCH (p:Project {slug: $slug})
        CREATE (c:Conversation {
            id: $conv_id,
            model: $model,
            url_or_site: $site,
            captured_at: $ts
        }),
        (p)-[:HAS_CONVERSATION]->(c)
        """,
        {
            "slug": project_slug,
            "conv_id": conv_id,
            "model": model or site,
            "site": url or site,
            "ts": captured_at,
        },
    )

    # 3. Chunk
    chunks = chunk_transcript(transcript)
    log.info("ingest[%s]: chunked into %d pieces", conv_id[:8], len(chunks))
    if not chunks:
        log.warning("ingest[%s]: empty transcript, no chunks created", conv_id[:8])
        return conv_id

    # 4. Embed + persist to Chroma
    chunk_texts = [c.text for c in chunks]
    from ..retrieval.embed import embed_texts
    embeddings = embed_texts(chunk_texts)
    chunk_ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {
            "chunk_ref": _id,
            "project_slug": project_slug,
            "source": url or site,
            "note_id": conv_id,  # link chunk → research note later
            "role": c.role,
            "chunk_index": c.chunk_index,
            "captured_at": captured_at,
        }
        for c, _id in zip(chunks, chunk_ids)
    ]
    dense.add_chunks(chunk_texts, embeddings, metadatas)
    log.info("ingest[%s]: wrote %d chunks to chroma", conv_id[:8], len(chunks))

    # 5. Add to BM25 (same metadata so dedup results look uniform)
    sparse.add(chunk_ids, chunk_texts, metadatas)

    # 6. Curator: extract structured entities/decisions/goals
    note_id = str(uuid.uuid4())
    summary = _first_words(transcript, 200)  # pre-summary before LLM call
    try:
        extracted = _curator_extract(transcript, project_slug, conv_id)
    except Exception:
        log.exception("ingest[%s]: curator extraction failed", conv_id[:8])
        # Per blueprint §4.2.4: fail loudly, don't silently drop.
        # We still write the ResearchNote so the transcript is searchable,
        # but we tag it as `extraction_status=failed` for visibility.
        extracted = {"decisions": [], "goals_mentioned": [], "entities": [], "status": "failed"}

    # 7. Write ResearchNote + Conversation + extracted graph nodes
    _write_research_note(
        note_id=note_id,
        conv_id=conv_id,
        project_slug=project_slug,
        summary=summary,
        source=url or site,
        captured_at=captured_at,
        first_chunk_ref=chunk_ids[0],
        extracted=extracted,
    )

    log.info(
        "ingest[%s]: complete. note=%s decisions=%d goals=%d entities=%d",
        conv_id[:8],
        note_id[:8],
        len(extracted.get("decisions", [])),
        len(extracted.get("goals_mentioned", [])),
        len(extracted.get("entities", [])),
    )
    return conv_id


def _ensure_project(slug: str) -> dict:
    rows = graph.run_read("MATCH (p:Project {slug: $slug}) RETURN p", {"slug": slug})
    if rows:
        return {"id": rows[0]["p"].get("id"), "slug": slug}
    # Create empty project if caller didn't pre-create it (defensive).
    new_id = str(uuid.uuid4())
    graph.run_write(
        """
        CREATE (p:Project {id: $id, name: $name, slug: $slug,
                           created_at: $ts, status: 'active'})
        """,
        {
            "id": new_id,
            "name": slug,
            "slug": slug,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"id": new_id, "slug": slug}


def _write_research_note(
    note_id: str,
    conv_id: str,
    project_slug: str,
    summary: str,
    source: str,
    captured_at: str,
    first_chunk_ref: str,
    extracted: dict,
) -> None:
    graph.run_write(
        """
        MATCH (p:Project {slug: $slug}), (c:Conversation {id: $conv_id})
        CREATE (r:ResearchNote {
            id: $note_id,
            summary: $summary,
            source: $source,
            created_at: $ts,
            chunk_ref: $chunk_ref,
            extraction_status: $status
        }),
        (p)-[:HAS_RESEARCH]->(r),
        (r)-[:FROM]->(c)
        """,
        {
            "slug": project_slug,
            "conv_id": conv_id,
            "note_id": note_id,
            "summary": summary,
            "source": source,
            "ts": captured_at,
            "chunk_ref": first_chunk_ref,
            "status": extracted.get("status", "ok"),
        },
    )

    # Decisions
    for d in extracted.get("decisions", []):
        did = str(uuid.uuid4())
        text = d if isinstance(d, str) else d.get("text", "")
        graph.run_write(
            """
            MATCH (p:Project {slug: $slug})
            MERGE (d:Decision {id: $id, text: $text, created_at: $ts})
            MERGE (p)-[:HAS_DECISION]->(d)
            """,
            {"slug": project_slug, "id": did, "text": text, "ts": captured_at},
        )

    # Goals
    for g in extracted.get("goals_mentioned", []):
        text = g if isinstance(g, str) else g.get("text", "")
        existing = graph.run_read(
            "MATCH (p:Project {slug: $slug})-[:HAS_GOAL]->(g:Goal {text: $text}) RETURN g",
            {"slug": project_slug, "text": text},
        )
        if existing:
            continue
        gid = str(uuid.uuid4())
        graph.run_write(
            """
            MATCH (p:Project {slug: $slug})
            CREATE (g:Goal {id: $id, text: $text, created_at: $ts, active: true})
            CREATE (p)-[:HAS_GOAL]->(g)
            """,
            {"slug": project_slug, "id": gid, "text": text, "ts": captured_at},
        )

    # Entities
    for e in extracted.get("entities", []):
        if isinstance(e, str):
            name, etype = e, "unknown"
        else:
            name = e.get("name", "")
            etype = e.get("type", "unknown")
        if not name:
            continue
        graph.run_write(
            """
            MATCH (r:ResearchNote {id: $note_id})
            MERGE (e:Entity {name: $name, type: $type})
            MERGE (r)-[:MENTIONS]->(e)
            """,
            {"note_id": note_id, "name": name, "type": etype},
        )


def _first_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n])


def _curator_extract(transcript: str, project_slug: str, conv_id: str) -> dict:
    """Call CURATOR_MODEL_PROVIDER to extract structured signal.

    Returns dict: {decisions: [str], goals_mentioned: [str],
                   entities: [{name, type}], status: 'ok'}.
    Fails loudly — raises — if the model output doesn't parse.
    """
    from ..curator.brief import call_curator

    prompt = f"""You are reading a captured chat transcript to extract structured signal.
The transcript is from project "{project_slug}". Your job: pull out the durable
facts — decisions that were made, goals that came up, and named entities (tools,
libraries, people, products).

Return ONLY valid JSON, no prose, no markdown fences. Schema:
{{
  "decisions": ["<short text of each decision>", ...],
  "goals_mentioned": ["<short text of each goal>", ...],
  "entities": [{{"name": "<string>", "type": "<tool|library|person|product|concept|other>"}}]
}}

If a category is empty, return an empty list — never invent content.

TRANSCRIPT:
\"\"\"
{transcript[:8000]}
\"\"\"
"""
    raw = call_curator(prompt, max_tokens=2000, json_mode=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"curator returned non-JSON (conv={conv_id[:8]}): {e}\nraw[:200]={raw[:200]!r}")
    # Required keys must be present; fail loudly otherwise.
    for k in ("decisions", "goals_mentioned", "entities"):
        if k not in parsed:
            raise RuntimeError(f"curator output missing required key: {k!r}")
    parsed["status"] = "ok"
    return parsed

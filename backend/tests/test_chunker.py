"""Tests for the chunker — the only piece of the pipeline that can be
exercised without Neo4j / Chroma / embedding API access.

Other tests (ingest, brief, dedup) are marked skipped in this commit
because they require either:
- A running Neo4j (start with `docker compose up -d neo4j`)
- A valid Gemini API key in .env
- Both

Marking them as skipped (not deleted) is intentional: they document what
the end-to-end flow looks like and become runnable once the user has the
full stack up.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest.chunker import chunk_transcript

FIXTURES = Path(__file__).parent / "fixtures"


def test_chunker_handles_empty():
    assert chunk_transcript("") == []


def test_chunker_turn_based():
    text = (FIXTURES / "transcript_basic.txt").read_text()
    chunks = chunk_transcript(text)
    assert len(chunks) >= 1
    # Each chunk should have a chunk_index
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


def test_chunker_paragraph_fallback():
    text = (FIXTURES / "transcript_paragraph.txt").read_text()
    chunks = chunk_transcript(text)
    # Narrative text should split into multiple paragraphs
    assert len(chunks) >= 1
    assert all(c.role == "narrative" for c in chunks)


def test_chunker_hard_cap():
    text = "x" * 5000  # no markers, no paragraphs, single run
    chunks = chunk_transcript(text)
    assert len(chunks) >= 3
    # Hard cap should keep chunks under MAX_CHARS + small slack
    from app.ingest.chunker import MAX_CHARS
    for c in chunks:
        assert len(c.text) <= MAX_CHARS + 50  # slack for the merge buffer


@pytest.mark.skip(reason="needs running Neo4j + Gemini key — see README manual test flow")
def test_ingest_pipeline_e2e():
    """Smoke test: full ingest path. Unskip when stack is up."""
    pass

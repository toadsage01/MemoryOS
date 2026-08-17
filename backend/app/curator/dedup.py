"""Dedup scoring (§4.5 of the blueprint).

Given a candidate question/topic:
1. Hybrid-retrieve against ResearchNote-derived chunks only.
2. If top fused score is above threshold → return overlap signal.
3. Otherwise → no overlap.

Threshold (DEDUP_FUSED_SCORE_THRESHOLD) is a STARTING VALUE, not validated.
Tune against a few real test cases.
"""
from __future__ import annotations

import logging

from ..config import get_settings
from ..retrieval import hybrid

log = logging.getLogger(__name__)


def check_overlap(project_slug: str, candidate: str) -> dict:
    """Return either:
        {overlap: true,  note_summary, note_date, note_id, score}
        {overlap: false, score}
    """
    s = get_settings()
    # Restrict to chunks tagged with this project_slug.
    hits = hybrid.retrieve(candidate, top_k=5, where={"project_slug": project_slug})
    if not hits:
        return {"overlap": False, "score": 0.0, "note_id": None}
    top = hits[0]
    score = top["fused_score"]
    if score > s.dedup_fused_score_threshold:
        return {
            "overlap": True,
            "note_summary": _summarize_chunk(top["document"]),
            "note_date": top["metadata"].get("captured_at"),
            "note_id": top["metadata"].get("note_id"),
            "score": score,
        }
    return {"overlap": False, "score": score, "note_id": top["metadata"].get("note_id")}


def _summarize_chunk(text: str) -> str:
    """Quick summary of a chunk — just first ~120 chars, no LLM call needed."""
    text = text.strip()
    if len(text) <= 120:
        return text
    # Cut on word boundary
    cut = text[:120].rsplit(" ", 1)[0]
    return cut + "..."

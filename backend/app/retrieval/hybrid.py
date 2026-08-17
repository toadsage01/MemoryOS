"""Hybrid retrieval — reciprocal rank fusion (§4.3 of the blueprint).

Run dense + sparse in parallel, fuse with RRF:
    score = 1 / (60 + dense_rank) + 1 / (60 + sparse_rank)

No tuning needed at this stage — that's the whole point of RRF.
"""
from __future__ import annotations

import logging
from typing import Sequence

from . import dense, sparse
from .embed import embed_text

log = logging.getLogger(__name__)

RRF_K = 60  # standard reciprocal rank fusion constant


def retrieve(
    query_text: str,
    top_k: int = 10,
    where: dict | None = None,
    restrict_to_note_ids: Sequence[str] | None = None,
) -> list[dict]:
    """Hybrid retrieve. Returns a list of dicts sorted by fused score desc:

    {id, document, metadata, fused_score, dense_rank, sparse_rank}
    """
    # Dense
    q_emb = embed_text(query_text)
    dense_hits = dense.query_dense(q_emb, top_k=max(top_k * 3, top_k), where=where)
    # Sparse
    sparse_hits = sparse.query(query_text, top_k=max(top_k * 3, top_k))

    # Optional filter to a specific set of notes (used by /dedup-check).
    if restrict_to_note_ids is not None:
        allowed = set(restrict_to_note_ids)
        dense_hits = [h for h in dense_hits if h.get("metadata", {}).get("note_id") in allowed]
        sparse_hits = [h for h in sparse_hits if h.get("metadata", {}).get("note_id") in allowed]

    # Build rank maps
    dense_rank = {h["id"]: i for i, h in enumerate(dense_hits)}
    sparse_rank = {h["id"]: i for i, h in enumerate(sparse_hits)}

    # Collect candidate ids (union)
    all_ids = set(dense_rank) | set(sparse_rank)

    # Look up hit dicts by id
    by_id: dict[str, dict] = {}
    for h in dense_hits:
        by_id[h["id"]] = h
    for h in sparse_hits:
        if h["id"] in by_id:
            # merge metadata
            by_id[h["id"]]["metadata"] = {**by_id[h["id"]].get("metadata", {}), **h.get("metadata", {})}
        else:
            by_id[h["id"]] = h

    fused = []
    for _id in all_ids:
        dr = dense_rank.get(_id)
        sr = sparse_rank.get(_id)
        score = 0.0
        if dr is not None:
            score += 1.0 / (RRF_K + dr)
        if sr is not None:
            score += 1.0 / (RRF_K + sr)
        h = by_id[_id]
        fused.append(
            {
                "id": _id,
                "document": h.get("document", ""),
                "metadata": h.get("metadata", {}),
                "fused_score": score,
                "dense_rank": dr,
                "sparse_rank": sr,
            }
        )
    fused.sort(key=lambda r: -r["fused_score"])
    return fused[:top_k]

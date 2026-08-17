"""ChromaDB dense-vector store.

Embedded persistent client — no separate process needed at this scale
(per §6 of the blueprint). Each chunk gets:
- its embedding (from embed.py)
- its text
- metadata: {chunk_ref, project_slug, source, note_id, created_at, role}
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

import chromadb
from chromadb.api.models.Collection import Collection

from ..config import get_settings

log = logging.getLogger(__name__)

_collection: Collection | None = None


def _get_collection() -> Collection:
    global _collection
    if _collection is None:
        s = get_settings()
        client = chromadb.PersistentClient(path=str(s.chroma_path))
        _collection = client.get_or_create_collection(
            name=s.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        log.info(
            "opened chroma collection %r at %s (count=%d)",
            s.chroma_collection,
            s.chroma_path,
            _collection.count(),
        )
    return _collection


def add_chunks(
    texts: Sequence[str],
    embeddings: Sequence[list[float]],
    metadatas: Sequence[dict],
) -> list[str]:
    """Upsert chunks. Returns the list of generated ids (in order)."""
    if not texts:
        return []
    assert len(texts) == len(embeddings) == len(metadatas)
    ids = [str(uuid.uuid4()) for _ in texts]
    col = _get_collection()
    col.add(
        ids=ids,
        documents=list(texts),
        embeddings=list(embeddings),
        metadatas=[_clean_meta(m) for m in metadatas],
    )
    return ids


def query_dense(
    query_embedding: list[float],
    top_k: int = 10,
    where: dict | None = None,
) -> list[dict]:
    """Return top-k chunks by cosine similarity. Each result dict:
    {id, document, metadata, distance}."""
    col = _get_collection()
    res = col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )
    # Chroma returns lists-of-lists even for single-query.
    out = []
    if not res.get("ids") or not res["ids"][0]:
        return out
    for i, _id in enumerate(res["ids"][0]):
        out.append(
            {
                "id": _id,
                "document": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "distance": res["distances"][0][i],
            }
        )
    return out


def count() -> int:
    """Total chunk count."""
    return _get_collection().count()


def _clean_meta(m: dict) -> dict:
    """Chroma rejects None values; coerce everything to str."""
    out = {}
    for k, v in m.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out

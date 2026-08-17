"""BM25 sparse index.

A tiny in-memory index using `rank_bm25`. The corpus lives in the same
process as the rest of the backend; persisted to disk on every upsert so
restarts pick up where the last ingest left off.

Why not Chroma's own BM25? It's been on/off the roadmap; the standalone
`rank-bm25` package is small, stable, and gives us full control of the
fusion score layout. Swap later if a better option appears.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Sequence

from rank_bm25 import BM25Okapi

from ..config import get_settings

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Index:
    """In-memory BM25 over (id, text, metadata) triples. Disk-persisted."""

    def __init__(self, persist_path: Path) -> None:
        self.persist_path = persist_path
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._docs: list[dict] = []  # {id, text, metadata, tokens}
        self._bm25: BM25Okapi | None = None
        self._load()

    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self._docs = data
            self._rebuild()
            log.info("bm25: loaded %d docs from %s", len(self._docs), self.persist_path)
        except Exception:
            log.exception("bm25: failed to load persisted index, starting fresh")
            self._docs = []

    def _save(self) -> None:
        tmp = self.persist_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._docs), encoding="utf-8")
        tmp.replace(self.persist_path)

    def _rebuild(self) -> None:
        if not self._docs:
            self._bm25 = None
            return
        self._bm25 = BM25Okapi([d["tokens"] for d in self._docs])

    def add(self, ids: Sequence[str], texts: Sequence[str], metadatas: Sequence[dict]) -> None:
        existing = {d["id"] for d in self._docs}
        for _id, text, meta in zip(ids, texts, metadatas):
            if _id in existing:
                # replace in place
                for i, d in enumerate(self._docs):
                    if d["id"] == _id:
                        self._docs[i] = {
                            "id": _id,
                            "text": text,
                            "metadata": meta,
                            "tokens": _tokenize(text),
                        }
                        break
            else:
                self._docs.append(
                    {
                        "id": _id,
                        "text": text,
                        "metadata": meta,
                        "tokens": _tokenize(text),
                    }
                )
        self._rebuild()
        self._save()

    def query(self, query_text: str, top_k: int = 10) -> list[dict]:
        """Return top-k hits with their rank (0=best)."""
        if self._bm25 is None or not self._docs:
            return []
        tokens = _tokenize(query_text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # argsort descending
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for rank, idx in enumerate(ranked[:top_k]):
            if scores[idx] <= 0:
                break  # no real overlap
            out.append(
                {
                    "id": self._docs[idx]["id"],
                    "document": self._docs[idx]["text"],
                    "metadata": self._docs[idx]["metadata"],
                    "score": float(scores[idx]),
                    "rank": rank,
                }
            )
        return out

    def count(self) -> int:
        return len(self._docs)


# ── Module-level singleton ───────────────────────────────────────────────
_index: BM25Index | None = None


def get_index() -> BM25Index:
    global _index
    if _index is None:
        s = get_settings()
        path = Path(s.chroma_persist_dir) / "bm25.json"
        if not path.is_absolute():
            path = Path("../" + str(path))
        # Resolve relative to repo root
        from ..config import REPO_ROOT

        if not Path(s.chroma_persist_dir).is_absolute():
            path = REPO_ROOT / s.chroma_persist_dir / "bm25.json"
        _index = BM25Index(path)
    return _index


def add(ids: Sequence[str], texts: Sequence[str], metadatas: Sequence[dict]) -> None:
    get_index().add(ids, texts, metadatas)


def query(query_text: str, top_k: int = 10) -> list[dict]:
    return get_index().query(query_text, top_k=top_k)


def count() -> int:
    return get_index().count()

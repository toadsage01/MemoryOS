"""Embedding calls.

Default provider: Google Gemini `text-embedding-004` (free tier).
One HTTP call, no SDK lock-in — provider swaps are local to this file.

The fallback (`EMBEDDING_PROVIDER=local`) uses sentence-transformers
`all-MiniLM-L6-v2` running on the same process. Slower but free and offline.
"""
from __future__ import annotations

import logging
from typing import Sequence

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

# Gemini embedding endpoint (REST, no SDK needed).
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:batchEmbedContents?key={key}"
)

# Cached local model handle (heavy — load once per process).
_LOCAL_MODEL = None


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text, in order."""
    texts = list(texts)
    if not texts:
        return []
    s = get_settings()
    provider = s.embedding_provider.lower()
    if provider == "gemini":
        return _embed_gemini(texts)
    if provider == "local":
        return _embed_local(texts)
    raise ValueError(f"unknown embedding_provider: {provider!r}")


def embed_text(text: str) -> list[float]:
    """Convenience single-text wrapper around embed_texts."""
    return embed_texts([text])[0]


def _embed_gemini(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if not s.embedding_api_key:
        raise RuntimeError(
            "EMBEDDING_API_KEY is empty — set it in .env to use Gemini embeddings. "
            "Or switch EMBEDDING_PROVIDER=local to use sentence-transformers offline."
        )
    body = {
        "requests": [
            {
                "model": f"models/{s.embedding_model}",
                "content": {"parts": [{"text": t}]},
                "taskType": "RETRIEVAL_DOCUMENT",
            }
            for t in texts
        ]
    }
    url = _GEMINI_URL.format(model=s.embedding_model, key=s.embedding_api_key)
    with httpx.Client(timeout=30.0) as c:
        r = c.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    return [item["values"] for item in data.get("embeddings", [])]


def _embed_local(texts: list[str]) -> list[list[float]]:
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        log.info("loading sentence-transformers all-MiniLM-L6-v2 (first call only)")
        from sentence_transformers import SentenceTransformer

        _LOCAL_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _LOCAL_MODEL.encode(texts, convert_to_numpy=False).tolist()

"""Chunker — simple turn/paragraph-based chunking per §4.2.

No fancy semantic chunking at this corpus size (hundreds to low thousands
of conversations). Split on:
1. Speaker turns if the transcript has clear user/assistant markers.
2. Otherwise, split on blank-line paragraph boundaries.
3. Otherwise, hard-cap on a character budget.

Each chunk keeps the conversation order (chunk_index) so retrieval can
reconstruct minimal context if needed later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Reasonable upper bound. ~400-500 words per chunk works well for both
# dense (embedding quality) and sparse (BM25 term statistics) retrieval.
MAX_CHARS = 1500
MIN_CHARS = 80  # below this, merge into the previous chunk

# Heuristics for "this looks like a chat transcript":
# - "User:" / "Assistant:" / "Human:" / "AI:" prefixes
# - "## User" / "## Assistant" markdown headers
# - Common Claude/ChatGPT/Gemini patterns
_TURN_RE = re.compile(
    r"^\s*(user|assistant|human|ai|you|claude|gemini|chatgpt)\s*[:\-\u2013]\s",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    text: str
    chunk_index: int
    role: str  # "user" | "assistant" | "narrative" | "unknown"
    turn_index: int | None  # within original transcript, if detectable


def chunk_transcript(text: str) -> list[Chunk]:
    """Split a transcript into chunks."""
    text = text.strip()
    if not text:
        return []
    # 1. Try speaker-turn split
    if _looks_like_turns(text):
        return _chunk_by_turns(text)
    # 2. Try paragraph split
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return _chunk_paragraphs(paragraphs)
    # 3. Hard char-cap
    return _chunk_hard(text)


def _looks_like_turns(text: str) -> bool:
    matches = _TURN_RE.findall(text, endpos=4000)
    return len(matches) >= 2  # at least two speaker markers


def _chunk_by_turns(text: str) -> list[Chunk]:
    # Split into (role, content) pairs by walking the markers.
    matches = list(_TURN_RE.finditer(text))
    if not matches:
        return _chunk_paragraphs([text])
    turns: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        role = m.group(1).lower()
        # Normalize common aliases
        if role in {"human", "you"}:
            role = "user"
        elif role in {"ai"}:
            role = "assistant"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        turns.append((role, content))

    chunks: list[Chunk] = []
    buf: list[tuple[str, str]] = []
    buf_chars = 0
    chunk_index = 0
    turn_index = 0
    for role, content in turns:
        turn_index += 1
        if buf and buf_chars + len(content) > MAX_CHARS:
            # flush
            joined = "\n\n".join(f"{r.title()}: {c}" for r, c in buf)
            chunks.append(
                Chunk(
                    text=joined,
                    chunk_index=chunk_index,
                    role=buf[0][0],
                    turn_index=turn_index - len(buf),
                )
            )
            chunk_index += 1
            buf = []
            buf_chars = 0
        buf.append((role, content))
        buf_chars += len(content)
    if buf:
        joined = "\n\n".join(f"{r.title()}: {c}" for r, c in buf)
        chunks.append(
            Chunk(
                text=joined,
                chunk_index=chunk_index,
                role=buf[0][0],
                turn_index=turn_index - len(buf) + 1,
            )
        )
    return _merge_short(chunks)


def _chunk_paragraphs(paras: list[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_chars = 0
    chunk_index = 0
    for p in paras:
        if buf and buf_chars + len(p) > MAX_CHARS:
            chunks.append(Chunk(text="\n\n".join(buf), chunk_index=chunk_index, role="narrative", turn_index=None))
            chunk_index += 1
            buf = []
            buf_chars = 0
        buf.append(p)
        buf_chars += len(p)
    if buf:
        chunks.append(Chunk(text="\n\n".join(buf), chunk_index=chunk_index, role="narrative", turn_index=None))
    return _merge_short(chunks)


def _chunk_hard(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for i in range(0, len(text), MAX_CHARS):
        chunks.append(Chunk(text=text[i : i + MAX_CHARS], chunk_index=i, role="narrative", turn_index=None))
    return chunks


def _merge_short(chunks: list[Chunk]) -> list[Chunk]:
    """If a chunk is below MIN_CHARS, merge it into the previous one (if any)."""
    if len(chunks) < 2:
        return chunks
    out: list[Chunk] = [chunks[0]]
    for c in chunks[1:]:
        if len(c.text) < MIN_CHARS and out:
            prev = out[-1]
            prev.text = prev.text + "\n\n" + c.text
        else:
            out.append(c)
    # reindex chunk_index
    for i, c in enumerate(out):
        c.chunk_index = i
    return out

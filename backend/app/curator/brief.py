"""Brief generation (§4.4 of the blueprint).

Given a project slug:
1. Pull active goals + last N decisions from the graph (no retrieval needed).
2. Hybrid-retrieve the most relevant research notes for "what's likely
   relevant right now" (use the last few captured conversation turns as the
   query if available, otherwise just recent + high-centrality notes).
3. Have CURATOR_MODEL_PROVIDER compress goals + decisions + retrieved notes
   into a SHORT brief — target ~150-300 words. HARD constraint.
4. Return plain text, ready to paste into a prompt.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .. import graph
from ..config import get_settings
from ..retrieval import hybrid

log = logging.getLogger(__name__)

# How many recent decisions to include. N bigger = more durable context.
_RECENT_DECISIONS_N = 5
_RECENT_GOALS_N = 5
_RETRIEVAL_TOPK = 6
# How much transcript text to use as the query (recent turns).
_QUERY_TURN_CHARS = 800


def make_brief(project_slug: str, recent_turns: str | None = None) -> str:
    """Return a sub-300-word plain-text brief."""
    s = get_settings()
    # 1. Pull structured facts from the graph
    goals = _pull_goals(project_slug, _RECENT_GOALS_N)
    decisions = _pull_decisions(project_slug, _RECENT_DECISIONS_N)

    # 2. Hybrid retrieve
    query_text = recent_turns.strip() if recent_turns else _compose_query(goals, decisions)
    retrieved = hybrid.retrieve(query_text, top_k=_RETRIEVAL_TOPK) if query_text else []

    if not goals and not decisions and not retrieved:
        return (
            f"[no memory yet for project '{project_slug}' — "
            f"this is a fresh context block]"
        )

    # 3. Compose prompt
    prompt = _compose_prompt(project_slug, goals, decisions, retrieved)
    raw_brief = _curator_summarize(prompt)

    # 4. Truncate to brief_max_words, never silently overflow
    brief = _truncate_to_words(raw_brief, s.brief_max_words)
    if brief != raw_brief:
        brief = brief.rstrip(".") + ". [truncated]"
    return brief


def _pull_goals(slug: str, n: int) -> list[str]:
    rows = graph.run_read(
        """
        MATCH (p:Project {slug: $slug})-[:HAS_GOAL]->(g:Goal)
        WHERE g.active = true
        RETURN g.text AS text
        ORDER BY g.created_at DESC
        LIMIT $n
        """,
        {"slug": slug, "n": n},
    )
    return [r["text"] for r in rows if r.get("text")]


def _pull_decisions(slug: str, n: int) -> list[str]:
    rows = graph.run_read(
        """
        MATCH (p:Project {slug: $slug})-[:HAS_DECISION]->(d:Decision)
        RETURN d.text AS text, d.created_at AS ts
        ORDER BY d.created_at DESC
        LIMIT $n
        """,
        {"slug": slug, "n": n},
    )
    return [r["text"] for r in rows if r.get("text")]


def _compose_query(goals: list[str], decisions: list[str]) -> str:
    """Fallback query when the extension doesn't send recent_turns."""
    parts = []
    if goals:
        parts.extend(goals[:3])
    if decisions:
        parts.extend(decisions[:3])
    return " ".join(parts)


def _compose_prompt(slug: str, goals: list[str], decisions: list[str], retrieved: list[dict]) -> str:
    goal_block = "\n".join(f"- {g}" for g in goals) if goals else "- (none yet)"
    dec_block = "\n".join(f"- {d}" for d in decisions) if decisions else "- (none yet)"
    note_block = "\n\n".join(
        f"--- research chunk [{i + 1}] ---\n{c['document'][:600]}"
        for i, c in enumerate(retrieved)
    ) if retrieved else "(no research retrieved)"

    return f"""You are the project memory for "{slug}". Compose a brief that another LLM
can paste at the top of a fresh conversation to get oriented instantly.

HARD CONSTRAINT: keep the brief under 300 words. If you can't fit everything,
prioritize: open decisions > active goals > relevant research notes > entities.
Do NOT explain what you're doing — output the brief, ready to paste.

Active goals:
{goal_block}

Recent decisions:
{dec_block}

Most relevant research retrieved (chunks):
{note_block}

Output the brief now, plain text, no markdown, under 300 words.
"""


def _curator_summarize(prompt: str) -> str:
    """Call the curator. Fail loudly if it breaks."""
    from .llm import call_curator

    return call_curator(
        prompt,
        max_tokens=600,
        temperature=0.2,
        system="You are a concise memory curator. You never pad.",
    )


def _truncate_to_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])

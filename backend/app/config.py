"""Application configuration — single source of truth for env-loaded settings.

Reads from .env (gitignored). If a required secret is missing the app still
boots, but the affected subsystem logs a clear notice and refuses the call
that needs it (fail loudly, never silently — §1.1 of the blueprint).
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root — backend/app/config.py → ../../ = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Backend runtime ───────────────────────────────────────────────
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # ── Local auth (§5) ───────────────────────────────────────────────
    # Empty on first run → boot will mint one and write it back to .env
    local_auth_token: str = ""

    # ── Neo4j ─────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ── ChromaDB ──────────────────────────────────────────────────────
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "second_brain_chunks"

    # ── Embedding ─────────────────────────────────────────────────────
    embedding_provider: str = "gemini"
    embedding_model: str = "gemini-text-embedding-004"
    embedding_api_key: str = ""

    # ── Curator model ────────────────────────────────────────────────
    curator_model_provider: str = "gemini"
    curator_model_name: str = "gemini-2.0-flash"
    curator_api_key: str = ""

    # ── Tunables (labelled as starting points per §4.5) ───────────────
    dedup_fused_score_threshold: float = 0.7
    brief_max_words: int = 300

    @property
    def chroma_path(self) -> Path:
        """Absolute path to chroma persist dir, mkdir'd on first access."""
        # Resolve relative to repo root, not cwd.
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            p = REPO_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ensure_auth_token(self) -> str:
        """Mint a token if missing, persist back to .env so the extension can read it."""
        if self.local_auth_token:
            return self.local_auth_token
        new_token = secrets.token_urlsafe(32)
        self.local_auth_token = new_token
        _write_env_value("LOCAL_AUTH_TOKEN", new_token)
        return new_token


def _write_env_value(key: str, value: str) -> None:
    """Set/replace a key in .env in-place. Creates the file if absent."""
    env_path = REPO_ROOT / ".env"
    lines: list[str] = []
    found = False
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            if raw.startswith(f"{key}=") or raw.startswith(f"{key} ="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Curator model calls.

Default provider: Google Gemini 2.0 Flash (free tier). One HTTP call, no
SDK lock-in — provider swaps are local to this file. Switch to OpenAI,
Anthropic, or a local Ollama model by editing two functions below.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)


def call_curator(
    prompt: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    json_mode: bool = False,
    system: str | None = None,
) -> str:
    """Call the configured CURATOR_MODEL_PROVIDER. Returns the model's text response.

    Fail loudly — raise — on any error, including HTTP non-2xx and parse failures.
    The ingest pipeline relies on this for entity extraction; silent failures
    there would silently drop decisions/goals/entities (per §1.1).
    """
    s = get_settings()
    provider = s.curator_model_provider.lower()
    if provider == "gemini":
        return _call_gemini(prompt, max_tokens, temperature, json_mode, system)
    if provider == "mock":
        # Used in tests; not for production ingest.
        return json.dumps({"decisions": [], "goals_mentioned": [], "entities": []}) \
            if json_mode else "[mock response]"
    raise ValueError(f"unknown curator_model_provider: {provider!r}")


def _call_gemini(
    prompt: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    system: str | None,
) -> str:
    s = get_settings()
    if not s.curator_api_key:
        raise RuntimeError(
            "CURATOR_API_KEY is empty — set it in .env. "
            "Or set CURATOR_MODEL_PROVIDER=mock for tests only."
        )
    body: dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]},
        ],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = _GEMINI_URL.format(model=s.curator_model_name, key=s.curator_api_key)
    with httpx.Client(timeout=60.0) as c:
        r = c.post(url, json=body)
        if r.status_code >= 400:
            raise RuntimeError(
                f"curator HTTP {r.status_code}: {r.text[:400]}"
            )
        data = r.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"curator returned unexpected shape: {e}\nfull: {data}") from e

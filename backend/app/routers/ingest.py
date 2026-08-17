"""Ingest router (§4.2 of the blueprint).

The /ingest endpoint accepts the raw transcript + project tag, kicks off
the pipeline as a BackgroundTask, returns immediately with the
conversation_id so the extension can show a confirmation.

The pipeline is fire-and-forget from the browser's perspective; it logs
all failures with the conversation_id prefix so problems are traceable.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from ..auth import require_token
from ..ingest import pipeline

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_token)])


class IngestIn(BaseModel):
    project_slug: str = Field(..., min_length=1)
    transcript: str = Field(..., min_length=1)
    site: str = Field(..., min_length=1)  # e.g. "claude.ai", "gemini.google.com"
    url: str | None = None  # full URL of the tab the transcript was captured from
    model: str | None = None  # which LLM the user was chatting with, if known


class IngestOut(BaseModel):
    conversation_id: str
    status: str  # "queued" — actual ingestion happens in background


@router.post("", response_model=IngestOut, status_code=202)
def ingest(payload: IngestIn, background: BackgroundTasks) -> IngestOut:
    conv_id = str(uuid.uuid4())
    log.info(
        "ingest queued: conv=%s project=%s site=%s transcript_chars=%d",
        conv_id[:8],
        payload.project_slug,
        payload.site,
        len(payload.transcript),
    )
    background.add_task(_safe_ingest, conv_id, payload)
    return IngestOut(conversation_id=conv_id, status="queued")


def _safe_ingest(conv_id: str, payload: IngestIn) -> None:
    """Run the pipeline, swallow + log all errors so background tasks don't crash."""
    try:
        pipeline.run_ingest(
            project_slug=payload.project_slug,
            transcript=payload.transcript,
            site=payload.site,
            url=payload.url,
            model=payload.model,
            conv_id=conv_id,
        )
    except Exception:
        log.exception("ingest pipeline crashed conv=%s project=%s", conv_id[:8], payload.project_slug)

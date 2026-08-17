"""Dedup router — `/dedup-check` (§4.5 of the blueprint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import require_token
from ..curator import dedup

router = APIRouter(prefix="/dedup-check", tags=["dedup"], dependencies=[Depends(require_token)])


class DedupIn(BaseModel):
    project_slug: str = Field(..., min_length=1)
    candidate: str = Field(..., min_length=1)  # the question/topic being asked


class DedupOut(BaseModel):
    overlap: bool
    score: float
    note_id: str | None = None
    note_summary: str | None = None
    note_date: str | None = None


@router.post("", response_model=DedupOut)
def check(payload: DedupIn) -> DedupOut:
    result = dedup.check_overlap(payload.project_slug, payload.candidate)
    return DedupOut(
        overlap=result["overlap"],
        score=result["score"],
        note_id=result.get("note_id"),
        note_summary=result.get("note_summary"),
        note_date=result.get("note_date"),
    )

"""Context router — `/context/brief` (§4.4 of the blueprint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import require_token
from ..curator import brief

router = APIRouter(prefix="/context", tags=["context"], dependencies=[Depends(require_token)])


class BriefIn(BaseModel):
    project_slug: str = Field(..., min_length=1)
    # Optional: the last few conversation turns the user just typed, used as
    # the retrieval query for "what's likely relevant right now".
    recent_turns: str | None = None


class BriefOut(BaseModel):
    project_slug: str
    brief: str
    word_count: int


@router.post("/brief", response_model=BriefOut)
def make_brief(payload: BriefIn) -> BriefOut:
    text = brief.make_brief(payload.project_slug, payload.recent_turns)
    return BriefOut(
        project_slug=payload.project_slug,
        brief=text,
        word_count=len(text.split()),
    )

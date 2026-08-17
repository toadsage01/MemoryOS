"""Project router — minimal CRUD for projects.

The blueprint doesn't ask for project CRUD explicitly, but /ingest and
/context/brief both reference a project_slug, and the extension's popup
needs to list + create projects. This router covers exactly that.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import graph
from ..auth import require_token

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(require_token)])


class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-_]*$")
    status: str = "active"


class ProjectOut(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: str


@router.get("", response_model=list[ProjectOut])
def list_projects() -> list[ProjectOut]:
    rows = graph.run_read(
        "MATCH (p:Project) RETURN p.id AS id, p.name AS name, p.slug AS slug, "
        "p.status AS status, p.created_at AS created_at ORDER BY p.created_at DESC"
    )
    return [ProjectOut(**r) for r in rows]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(p: ProjectIn) -> ProjectOut:
    pid = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    try:
        graph.run_write(
            """
            CREATE (p:Project {id: $id, name: $name, slug: $slug,
                               created_at: $ts, status: $status})
            """,
            {"id": pid, "name": p.name, "slug": p.slug, "ts": ts, "status": p.status},
        )
    except Exception as e:
        # Likely constraint violation (duplicate slug)
        raise HTTPException(status_code=409, detail=f"project slug '{p.slug}' may already exist: {e}")
    return ProjectOut(id=pid, name=p.name, slug=p.slug, status=p.status, created_at=ts)

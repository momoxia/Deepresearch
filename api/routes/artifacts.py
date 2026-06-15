from fastapi import APIRouter, HTTPException

from api.deps import DBSession
from db import crud

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str, db: DBSession):
    art = await crud.get_artifact(db, artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="artifact 不存在")
    return {
        "artifact_id": art.artifact_id,
        "project_id": art.project_id,
        "session_id": art.session_id,
        "title": art.title,
        "code": art.code,
        "viz_hint": art.viz_hint,
        "created_at": art.created_at.isoformat() if art.created_at else None,
    }


@router.get("/by-project/{project_id}")
async def list_project_artifacts(project_id: int, db: DBSession, limit: int = 50):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    items = await crud.list_artifacts_by_project(db, project_id, limit=limit)
    return [
        {
            "artifact_id": a.artifact_id,
            "title": a.title,
            "viz_hint": a.viz_hint,
            "session_id": a.session_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]

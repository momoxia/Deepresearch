from fastapi import APIRouter, HTTPException

from api.deps import DBSession
from db import crud
from memory.manager import MemoryManager
from schemas.project import MemoryCreate, MemoryUpdate, ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _serialize(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "folder_id": getattr(p, "folder_id", None),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, db: DBSession):
    data = body.model_dump(exclude_none=True)
    proj = await crud.create_project(db, data)
    return _serialize(proj)


@router.get("", response_model=list[dict])
async def list_projects(db: DBSession, skip: int = 0, limit: int = 50):
    rows = await crud.list_projects(db, skip=skip, limit=limit)
    return [_serialize(p) for p in rows]


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: DBSession):
    ok = await crud.delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return None


@router.get("/{project_id}")
async def get_project(project_id: int, db: DBSession):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _serialize(proj)


@router.patch("/{project_id}")
async def update_project(project_id: int, body: ProjectUpdate, db: DBSession):
    data = body.model_dump(exclude_none=True)
    proj = await crud.update_project(db, project_id, data)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _serialize(proj)


@router.get("/{project_id}/memory")
async def get_project_memory(
    project_id: int,
    db: DBSession,
    category: str | None = None,
    include_archived: bool = False,
):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    mgr = MemoryManager(db, project_id)
    if include_archived or not category:
        return await mgr.load_all(include_archived=include_archived)
    return await mgr.load(category)


@router.post("/{project_id}/memory")
async def add_project_memory(project_id: int, body: MemoryCreate, db: DBSession):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    mgr = MemoryManager(db, project_id)
    mem = await mgr.save(
        category=body.category,
        key=body.key,
        value=body.value,
        importance=body.importance,
        source="user_edit",
    )
    return {"id": mem.id, "key": mem.key, "category": mem.category}


@router.patch("/{project_id}/memory/{memory_id}")
async def update_project_memory(
    project_id: int, memory_id: int, body: MemoryUpdate, db: DBSession
):
    data = body.model_dump(exclude_none=True)
    mem = await crud.update_memory(db, memory_id, data)
    if not mem:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"id": mem.id, "key": mem.key, "updated": True}


@router.delete("/{project_id}/memory/{memory_id}", status_code=204)
async def delete_project_memory(project_id: int, memory_id: int, db: DBSession):
    ok = await crud.delete_memory(db, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return None

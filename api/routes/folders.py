import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import DBSession
from db import crud
from db.models import Conversation, Project
from memory.folder_suggester import suggest_folder_tree
from memory.manager import MemoryManager
from schemas.folder import (
    ApplyTreeBody,
    AssignProjectBody,
    FolderCreate,
    FolderUpdate,
    SuggestBody,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])


def _serialize(f) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "parent_id": f.parent_id,
        "sort_order": f.sort_order,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


@router.get("")
async def list_folders(db: DBSession):
    rows = await crud.list_folders(db)
    return [_serialize(f) for f in rows]


@router.post("", status_code=201)
async def create_folder(body: FolderCreate, db: DBSession):
    folder = await crud.create_folder(
        db, name=body.name, parent_id=body.parent_id, sort_order=body.sort_order
    )
    return _serialize(folder)


@router.patch("/{folder_id}")
async def update_folder(folder_id: int, body: FolderUpdate, db: DBSession):
    data = body.model_dump(exclude_unset=True)
    folder = await crud.update_folder(db, folder_id, data)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return _serialize(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, db: DBSession):
    ok = await crud.delete_folder(db, folder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return None


@router.post("/assign/{project_id}")
async def assign_project(project_id: int, body: AssignProjectBody, db: DBSession):
    proj = await crud.assign_project_folder(db, project_id, body.folder_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"id": proj.id, "folder_id": proj.folder_id}


def _stringify(v, limit: int = 100) -> str:
    import json as _json

    if v is None:
        return ""
    if isinstance(v, str):
        text = v
    else:
        try:
            text = _json.dumps(v, ensure_ascii=False)
        except Exception:
            text = str(v)
    text = text.replace("\n", " ").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


async def _build_project_profile(db, project: Project) -> dict:
    first = await db.execute(
        select(Conversation.content)
        .where(Conversation.project_id == project.id, Conversation.role == "user")
        .order_by(Conversation.created_at.asc())
        .limit(1)
    )
    snippet = first.scalar_one_or_none() or ""

    mgr = MemoryManager(db, project.id)
    mems = await mgr.load()
    by_cat: dict[str, list[dict]] = {}
    for m in mems:
        by_cat.setdefault(m["category"], []).append(m)

    def top(cat: str, n: int) -> list[dict]:
        return [
            {"key": m["key"], "value": _stringify(m["value"], 100)}
            for m in by_cat.get(cat, [])[:n]
        ]

    episodic_items = by_cat.get("episodic", [])
    episode_brief = ""
    if episodic_items:
        episode_brief = _stringify(episodic_items[0]["value"], 200)

    return {
        "id": project.id,
        "name": project.name,
        "title": project.name,
        "snippet": _stringify(snippet, 120),
        "semantic": top("semantic", 3),
        "procedural": top("procedural", 2),
        "preference": top("preference", 2),
        "episode_brief": episode_brief,
        "memory_count": len(mems),
    }


@router.post("/suggest")
async def suggest(body: SuggestBody, db: DBSession):
    proj_result = await db.execute(
        select(Project).order_by(Project.updated_at.desc())
    )
    projects = list(proj_result.scalars().all())

    if not projects:
        return {"folders": [], "assignments": [], "rationale": "当前没有对话"}

    payload_projects = []
    for p in projects:
        try:
            payload_projects.append(await _build_project_profile(db, p))
        except Exception:
            logger.warning("Profile build failed for project %s", p.id, exc_info=True)
            payload_projects.append(
                {"id": p.id, "name": p.name, "title": p.name, "snippet": ""}
            )

    try:
        result = await suggest_folder_tree(body.instruction, payload_projects)
    except Exception as e:
        logger.exception("Folder suggest failed")
        raise HTTPException(status_code=500, detail=f"智能分类失败：{e}")

    valid_ids = {p.id for p in projects}
    result["assignments"] = [
        a for a in result.get("assignments", []) if a.get("project_id") in valid_ids
    ]
    return result


@router.post("/apply")
async def apply_tree(body: ApplyTreeBody, db: DBSession):
    folders_spec = [f.model_dump() for f in body.folders]
    assignments = [a.model_dump() for a in body.assignments]
    res = await crud.replace_folder_tree(db, folders_spec, assignments)
    folders = await crud.list_folders(db)
    return {
        "folder_count": res["folder_count"],
        "folders": [_serialize(f) for f in folders],
    }

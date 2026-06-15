import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Artifact, Conversation, Folder, Memory, Project


async def create_project(db: AsyncSession, data: dict) -> Project:
    proj = Project(**data)
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj


async def get_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def update_project(db: AsyncSession, project_id: int, data: dict) -> Optional[Project]:
    proj = await get_project(db, project_id)
    if not proj:
        return None
    for key, value in data.items():
        if hasattr(proj, key):
            setattr(proj, key, value)
    await db.commit()
    await db.refresh(proj)
    return proj


async def delete_project(db: AsyncSession, project_id: int) -> bool:
    proj = await get_project(db, project_id)
    if not proj:
        return False
    for model in (Conversation, Memory):
        rows = await db.execute(select(model).where(model.project_id == project_id))
        for row in rows.scalars().all():
            await db.delete(row)
    await db.delete(proj)
    await db.commit()
    return True


async def list_projects(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[Project]:
    result = await db.execute(select(Project).offset(skip).limit(limit))
    return list(result.scalars().all())


async def add_conversation(
    db: AsyncSession,
    project_id: int,
    role: str,
    content: str,
    session_id: Optional[str] = None,
) -> Conversation:
    conv = Conversation(
        project_id=project_id, role=role, content=content, session_id=session_id
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_recent_conversations(
    db: AsyncSession, project_id: int, limit: int = 20
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return list(reversed(rows))


async def count_conversations(db: AsyncSession, project_id: int) -> int:
    result = await db.execute(
        select(Conversation).where(Conversation.project_id == project_id)
    )
    return len(result.scalars().all())


async def set_session_title(
    db: AsyncSession, project_id: int, session_id: str, title: str
) -> None:
    result = await db.execute(
        select(Conversation)
        .where(
            and_(
                Conversation.project_id == project_id,
                Conversation.session_id == session_id,
            )
        )
        .order_by(Conversation.created_at.asc())
        .limit(1)
    )
    conv = result.scalar_one_or_none()
    if conv:
        conv.title = title
        await db.commit()


async def get_session_title(
    db: AsyncSession, project_id: int, session_id: str
) -> Optional[str]:
    result = await db.execute(
        select(Conversation.title)
        .where(
            and_(
                Conversation.project_id == project_id,
                Conversation.session_id == session_id,
                Conversation.title != None,  # noqa: E711
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_sessions(db: AsyncSession, project_id: int) -> list[dict]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id)
        .order_by(Conversation.created_at.desc())
    )
    convs = result.scalars().all()

    sessions: dict[str, dict] = {}
    for c in convs:
        sid = c.session_id or "default"
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "title": None,
                "message_count": 0,
                "last_message_at": c.created_at.isoformat() if c.created_at else None,
            }
        sessions[sid]["message_count"] += 1
        if c.title and not sessions[sid]["title"]:
            sessions[sid]["title"] = c.title

    return list(sessions.values())


async def save_memory(
    db: AsyncSession,
    project_id: int,
    category: str,
    key: str,
    value: object,
    importance: float = 1.0,
    expires_at: Optional[datetime] = None,
    source: str = "conversation",
) -> Memory:
    existing = await db.execute(
        select(Memory).where(
            and_(
                Memory.project_id == project_id,
                Memory.key == key,
                Memory.archived == False,  # noqa: E712
            )
        )
    )
    mem = existing.scalar_one_or_none()
    value_json = json.dumps(value, ensure_ascii=False)
    if mem:
        mem.value_json = value_json
        mem.importance_score = importance
        mem.category = category
        mem.source = source
        if expires_at:
            mem.expires_at = expires_at
    else:
        mem = Memory(
            project_id=project_id,
            category=category,
            key=key,
            value_json=value_json,
            importance_score=importance,
            expires_at=expires_at,
            source=source,
        )
        db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return mem


async def upsert_memory(
    db: AsyncSession,
    project_id: int,
    action: str,
    category: str,
    key: str,
    value: object,
    importance: float = 0.7,
    source: str = "conversation",
) -> Optional[Memory]:
    existing = await db.execute(
        select(Memory).where(
            and_(
                Memory.project_id == project_id,
                Memory.key == key,
                Memory.archived == False,  # noqa: E712
            )
        )
    )
    mem = existing.scalar_one_or_none()

    if action == "DELETE":
        if mem:
            mem.archived = True
            await db.commit()
        return mem

    value_json = json.dumps(value, ensure_ascii=False)

    if action == "UPDATE" and mem:
        mem.value_json = value_json
        mem.importance_score = importance
        mem.category = category
        mem.source = f"{source}_update"
        await db.commit()
        await db.refresh(mem)
        return mem

    if action == "ADD" and not mem:
        mem = Memory(
            project_id=project_id,
            category=category,
            key=key,
            value_json=value_json,
            importance_score=importance,
            source=source,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        return mem

    if action == "ADD" and mem:
        mem.value_json = value_json
        mem.importance_score = max(mem.importance_score, importance)
        mem.source = f"{source}_update"
        await db.commit()
        await db.refresh(mem)
        return mem

    return mem


async def increment_memory_access(db: AsyncSession, memory_ids: list[int]) -> None:
    if not memory_ids:
        return
    now = datetime.now(timezone.utc)
    result = await db.execute(select(Memory).where(Memory.id.in_(memory_ids)))
    for mem in result.scalars().all():
        mem.access_count = (mem.access_count or 0) + 1
        mem.last_accessed_at = now
    await db.commit()


async def archive_stale_memories(
    db: AsyncSession,
    project_id: int,
    days_threshold: int = 90,
    importance_threshold: float = 0.5,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
    result = await db.execute(
        select(Memory).where(
            and_(
                Memory.project_id == project_id,
                Memory.archived == False,  # noqa: E712
                Memory.importance_score < importance_threshold,
                (
                    (Memory.last_accessed_at == None)  # noqa: E711
                    | (Memory.last_accessed_at < cutoff)
                ),
                (Memory.updated_at < cutoff),
            )
        )
    )
    archived_count = 0
    for mem in result.scalars().all():
        mem.archived = True
        archived_count += 1
    if archived_count:
        await db.commit()
    return archived_count


async def load_memories(
    db: AsyncSession, project_id: int, category: Optional[str] = None
) -> list[Memory]:
    query = select(Memory).where(
        and_(
            Memory.project_id == project_id,
            Memory.archived == False,  # noqa: E712
        )
    )
    if category:
        query = query.where(Memory.category == category)
    now = datetime.now(timezone.utc)
    query = query.where(
        (Memory.expires_at == None) | (Memory.expires_at > now)  # noqa: E711
    )
    query = query.order_by(Memory.importance_score.desc(), Memory.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def load_all_memories_for_project(
    db: AsyncSession, project_id: int, include_archived: bool = False
) -> list[Memory]:
    query = select(Memory).where(Memory.project_id == project_id)
    if not include_archived:
        query = query.where(Memory.archived == False)  # noqa: E712
    query = query.order_by(Memory.category, Memory.importance_score.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_memory(db: AsyncSession, memory_id: int) -> bool:
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    mem = result.scalar_one_or_none()
    if not mem:
        return False
    await db.delete(mem)
    await db.commit()
    return True


async def create_artifact(
    db: AsyncSession,
    artifact_id: str,
    project_id: int,
    code: str,
    session_id: Optional[str] = None,
    title: Optional[str] = None,
    viz_hint: Optional[str] = None,
    research_content: Optional[str] = None,
) -> Artifact:
    art = Artifact(
        artifact_id=artifact_id,
        project_id=project_id,
        session_id=session_id,
        title=title,
        code=code,
        viz_hint=viz_hint,
        research_content=research_content,
    )
    db.add(art)
    await db.commit()
    await db.refresh(art)
    return art


async def get_artifact(db: AsyncSession, artifact_id: str) -> Optional[Artifact]:
    result = await db.execute(
        select(Artifact).where(Artifact.artifact_id == artifact_id)
    )
    return result.scalar_one_or_none()


async def list_artifacts_by_project(
    db: AsyncSession, project_id: int, limit: int = 50
) -> list[Artifact]:
    result = await db.execute(
        select(Artifact)
        .where(Artifact.project_id == project_id)
        .order_by(Artifact.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_folders(db: AsyncSession) -> list[Folder]:
    result = await db.execute(
        select(Folder).order_by(Folder.parent_id, Folder.sort_order, Folder.id)
    )
    return list(result.scalars().all())


async def get_folder(db: AsyncSession, folder_id: int) -> Optional[Folder]:
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    return result.scalar_one_or_none()


async def create_folder(
    db: AsyncSession,
    name: str,
    parent_id: Optional[int] = None,
    sort_order: int = 0,
) -> Folder:
    folder = Folder(name=name, parent_id=parent_id, sort_order=sort_order)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def update_folder(
    db: AsyncSession, folder_id: int, data: dict
) -> Optional[Folder]:
    folder = await get_folder(db, folder_id)
    if not folder:
        return None
    for key, value in data.items():
        if key in {"name", "parent_id", "sort_order"} and hasattr(folder, key):
            setattr(folder, key, value)
    await db.commit()
    await db.refresh(folder)
    return folder


async def delete_folder(db: AsyncSession, folder_id: int) -> bool:
    folder = await get_folder(db, folder_id)
    if not folder:
        return False
    parent_id = folder.parent_id

    child_result = await db.execute(
        select(Folder).where(Folder.parent_id == folder_id)
    )
    for child in child_result.scalars().all():
        child.parent_id = parent_id

    proj_result = await db.execute(
        select(Project).where(Project.folder_id == folder_id)
    )
    for proj in proj_result.scalars().all():
        proj.folder_id = parent_id

    await db.delete(folder)
    await db.commit()
    return True


async def assign_project_folder(
    db: AsyncSession, project_id: int, folder_id: Optional[int]
) -> Optional[Project]:
    proj = await get_project(db, project_id)
    if not proj:
        return None
    proj.folder_id = folder_id
    await db.commit()
    await db.refresh(proj)
    return proj


async def replace_folder_tree(
    db: AsyncSession,
    folders_spec: list[dict],
    assignments: list[dict],
) -> dict:
    """
    Bulk replace: delete all folders, create fresh ones from spec, apply project assignments.
    folders_spec: [{"tmp_id": "a1", "name": "...", "parent_tmp_id": "a2"|None, "sort_order": 0}, ...]
    assignments: [{"project_id": 1, "folder_tmp_id": "a1"|None}, ...]
    Returns: {"tmp_to_real": {tmp_id: real_id}, "folder_count": N}
    """
    existing = await db.execute(select(Folder))
    for f in existing.scalars().all():
        await db.delete(f)

    all_projs = await db.execute(select(Project))
    for p in all_projs.scalars().all():
        p.folder_id = None

    await db.flush()

    tmp_to_real: dict[str, int] = {}
    remaining = list(folders_spec)
    safety = 0
    while remaining and safety < 1000:
        safety += 1
        progressed = False
        next_remaining = []
        for spec in remaining:
            parent_tmp = spec.get("parent_tmp_id")
            parent_real = None
            if parent_tmp:
                if parent_tmp not in tmp_to_real:
                    next_remaining.append(spec)
                    continue
                parent_real = tmp_to_real[parent_tmp]
            folder = Folder(
                name=spec["name"],
                parent_id=parent_real,
                sort_order=spec.get("sort_order", 0),
            )
            db.add(folder)
            await db.flush()
            tmp_to_real[spec["tmp_id"]] = folder.id
            progressed = True
        remaining = next_remaining
        if not progressed:
            break

    for spec in remaining:
        folder = Folder(
            name=spec["name"], parent_id=None, sort_order=spec.get("sort_order", 0)
        )
        db.add(folder)
        await db.flush()
        tmp_to_real[spec["tmp_id"]] = folder.id

    for assign in assignments:
        pid = assign.get("project_id")
        tmp = assign.get("folder_tmp_id")
        folder_real = tmp_to_real.get(tmp) if tmp else None
        proj = await get_project(db, pid)
        if proj:
            proj.folder_id = folder_real

    await db.commit()
    return {"tmp_to_real": tmp_to_real, "folder_count": len(tmp_to_real)}


async def update_memory(
    db: AsyncSession, memory_id: int, data: dict
) -> Optional[Memory]:
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    mem = result.scalar_one_or_none()
    if not mem:
        return None
    for key, value in data.items():
        if key == "value":
            mem.value_json = json.dumps(value, ensure_ascii=False)
        elif hasattr(mem, key):
            setattr(mem, key, value)
    await db.commit()
    await db.refresh(mem)
    return mem

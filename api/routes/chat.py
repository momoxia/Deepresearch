import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import DBSession
from db.database import AsyncSessionLocal
from db import crud
from memory.manager import MemoryManager
from memory.title_generator import generate_title
from schemas.chat import ChatRequest, ChatResponse
from schemas.project import DEFAULT_PROJECT_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, db: DBSession):
    from agents.orchestrator import run_chat

    proj = await crud.get_project(db, body.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    mgr = MemoryManager(db, body.project_id)
    memory_context = await mgr.build_context_prompt(query_text=body.message)

    await crud.add_conversation(
        db,
        project_id=body.project_id,
        role="user",
        content=body.message,
        session_id=body.session_id,
    )

    reply, new_session_id = await run_chat(
        message=body.message,
        session_id=body.session_id,
        memory_context=memory_context,
        project_id=body.project_id,
    )

    await crud.add_conversation(
        db,
        project_id=body.project_id,
        role="assistant",
        content=reply,
        session_id=new_session_id,
    )

    new_messages = [
        {"role": "user", "content": body.message},
        {"role": "assistant", "content": reply},
    ]
    await mgr.process_after_conversation(new_messages)

    if new_session_id:
        existing_title = await crud.get_session_title(db, body.project_id, new_session_id)
        if not existing_title:
            title = await generate_title(body.message, reply)
            await crud.set_session_title(db, body.project_id, new_session_id, title)
            if proj.name == DEFAULT_PROJECT_NAME:
                await crud.update_project(db, body.project_id, {"name": title})

    return ChatResponse(
        project_id=body.project_id,
        session_id=new_session_id,
        reply=reply,
    )


@router.post("/stream")
async def chat_stream(body: ChatRequest, db: DBSession):
    from agents.orchestrator import run_chat_stream

    proj = await crud.get_project(db, body.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    mgr = MemoryManager(db, body.project_id)
    memory_context = await mgr.build_context_prompt(query_text=body.message)

    await crud.add_conversation(
        db,
        project_id=body.project_id,
        role="user",
        content=body.message,
        session_id=body.session_id,
    )

    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _pump_stream():
        """Run the model to completion; persist with a fresh DB session (survives client disconnect)."""
        final_reply = ""
        accumulated_text = ""
        final_session_id = body.session_id
        try:
            async for event in run_chat_stream(
                message=body.message,
                session_id=body.session_id,
                memory_context=memory_context,
                project_id=body.project_id,
            ):
                evt_type = event.get("type", "")
                if evt_type == "text":
                    accumulated_text += event.get("content", "")
                elif evt_type == "session":
                    final_session_id = event.get("session_id", final_session_id)
                elif evt_type == "done":
                    final_reply = event.get("reply", "")
                    final_session_id = event.get("session_id", final_session_id)
                await event_queue.put(event)
        except asyncio.CancelledError:
            logger.warning(
                "chat stream pump cancelled for project %s", body.project_id
            )
        except Exception:
            logger.exception("chat stream pump failed for project %s", body.project_id)
        finally:
            reply_to_persist = final_reply or accumulated_text
            if reply_to_persist:
                try:
                    async with AsyncSessionLocal() as persist_db:
                        await crud.add_conversation(
                            persist_db,
                            project_id=body.project_id,
                            role="assistant",
                            content=reply_to_persist,
                            session_id=final_session_id,
                        )
                    _schedule_memory_processing(
                        body.project_id,
                        body.message,
                        reply_to_persist,
                        session_id=final_session_id,
                    )
                except Exception:
                    logger.exception(
                        "Persist assistant reply after stream failed for project %s",
                        body.project_id,
                    )
            else:
                logger.warning(
                    "Stream ended with no reply for project %s session %s",
                    body.project_id,
                    final_session_id,
                )
            await event_queue.put(None)

    asyncio.create_task(_pump_stream())

    async def event_generator():
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_background_tasks: set[asyncio.Task] = set()


def _schedule_memory_processing(
    project_id: int,
    user_message: str,
    assistant_reply: str,
    session_id: str | None = None,
) -> None:

    async def _run():
        try:
            async with AsyncSessionLocal() as session:
                mgr = MemoryManager(session, project_id)
                new_messages = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_reply},
                ]
                await mgr.process_after_conversation(new_messages)

                if session_id:
                    existing_title = await crud.get_session_title(
                        session, project_id, session_id
                    )
                    if not existing_title:
                        title = await generate_title(user_message, assistant_reply)
                        await crud.set_session_title(
                            session, project_id, session_id, title
                        )
                        proj = await crud.get_project(session, project_id)
                        if proj and proj.name == DEFAULT_PROJECT_NAME:
                            await crud.update_project(
                                session, project_id, {"name": title}
                            )
        except Exception:
            logger.exception("Background memory processing failed for project %s", project_id)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.get("/{project_id}/history")
async def get_chat_history(project_id: int, db: DBSession, limit: int = 20):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    convs = await crud.get_recent_conversations(db, project_id, limit=limit)
    return [
        {
            "id": c.id,
            "role": c.role,
            "content": c.content,
            "session_id": c.session_id,
            "title": getattr(c, "title", None),
            "created_at": c.created_at.isoformat(),
        }
        for c in convs
    ]


@router.get("/{project_id}/sessions")
async def get_sessions(project_id: int, db: DBSession):
    proj = await crud.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return await crud.list_sessions(db, project_id)


@router.get("/{project_id}/title")
async def get_session_title(project_id: int, db: DBSession, session_id: str | None = None):
    if not session_id:
        return {"title": None}
    title = await crud.get_session_title(db, project_id, session_id)
    return {"title": title}

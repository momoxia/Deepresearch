"""
Memory MCP tools: load_memory / save_memory (per project).
"""
import json
import logging

from claude_agent_sdk import tool

from db.database import AsyncSessionLocal
from db import crud

logger = logging.getLogger(__name__)


@tool(
    "load_memory",
    "加载当前研究项目的记忆，可按类别过滤（semantic / episodic / procedural / preference）",
    {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer"},
            "category": {
                "type": "string",
                "description": "可选：semantic、episodic、procedural、preference；不传返回全部活跃记忆",
            },
        },
        "required": ["project_id"],
    },
)
async def load_memory(args: dict) -> dict:
    project_id = int(args["project_id"])
    category = args.get("category") or None

    async with AsyncSessionLocal() as db:
        mems = await crud.load_memories(db, project_id, category)

    if not mems:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"项目 ID={project_id} 暂无"
                    f"{('[' + category + ']') if category else ''}记忆。",
                }
            ]
        }

    result = []
    for m in mems:
        try:
            value = json.loads(m.value_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("load_memory: corrupt value_json for memory id=%s, using raw", m.id)
            value = m.value_json
        result.append({
            "id": m.id,
            "category": m.category,
            "key": m.key,
            "value": value,
            "importance": m.importance_score,
        })

    return {
        "content": [
            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
        ]
    }


@tool(
    "save_memory",
    "保存一条记忆到当前研究项目（关键事实、偏好、流程等）",
    {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer"},
            "category": {
                "type": "string",
                "description": "semantic / episodic / procedural / preference",
                "enum": ["semantic", "episodic", "procedural", "preference"],
            },
            "key": {
                "type": "string",
                "description": "英文下划线键名，如 key_hypothesis / preferred_sources",
            },
            "value": {
                "type": "string",
                "description": "简洁中文或结构化文本",
            },
            "importance": {
                "type": "number",
                "description": "0~1，默认 0.8",
                "default": 0.8,
            },
        },
        "required": ["project_id", "category", "key", "value"],
    },
)
async def save_memory(args: dict) -> dict:
    project_id = int(args["project_id"])

    async with AsyncSessionLocal() as db:
        mem = await crud.save_memory(
            db,
            project_id=project_id,
            category=args["category"],
            key=args["key"],
            value=args["value"],
            importance=float(args.get("importance", 0.8)),
        )

    return {
        "content": [
            {
                "type": "text",
                "text": f"记忆已保存：[{mem.category}] {mem.key}",
            }
        ]
    }

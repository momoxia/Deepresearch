"""
Memory manager: MemCell, mem0-style upsert, decay scoring, scheduler, embeddings.
"""
import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import crud
from db.models import Memory
from memory.embedding import cosine_similarity, get_embedding, parse_embedding
from memory.fact_extractor import extract_facts
from memory.scheduler import detect_task_type, get_strategy
from memory.summarizer import summarize_conversations
from memory.topic_segmenter import segment_conversation

logger = logging.getLogger(__name__)


def _safe_json_load(raw: str | None, fallback: str = ""):
    """Parse JSON stored in value_json; return raw string on failure."""
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

DEFAULT_TOP_K = 20
RECENCY_DECAY = 0.95


def _compute_score(mem: Memory) -> float:
    importance = mem.importance_score or 0.5
    now = datetime.now(timezone.utc)

    ref_time = mem.last_accessed_at or mem.updated_at or mem.created_at
    if ref_time and ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)
    if ref_time:
        days_since = max(0, (now - ref_time).total_seconds() / 86400)
    else:
        days_since = 30
    recency_factor = math.pow(RECENCY_DECAY, days_since)

    access = mem.access_count or 0
    access_factor = min(1.0, 0.5 + 0.1 * access)

    return importance * recency_factor * access_factor


class MemoryManager:
    def __init__(self, db: AsyncSession, project_id: int):
        self.db = db
        self.project_id = project_id

    async def build_context_prompt(self, query_text: str = "") -> str:
        await crud.archive_stale_memories(self.db, self.project_id)

        all_mems = await crud.load_memories(self.db, self.project_id)
        if not all_mems:
            return ""

        task_type = detect_task_type(query_text) if query_text else "chitchat"
        strategy = get_strategy(task_type)
        top_k = strategy.get("top_k", DEFAULT_TOP_K)
        cat_weights: dict[str, float] = strategy.get("category_weights", {})

        query_emb = None
        if query_text:
            query_emb = await get_embedding(query_text)

        scored: list[tuple[Memory, float]] = []
        for m in all_mems:
            base_score = _compute_score(m)

            cat_w = cat_weights.get(m.category, 0.7)
            base_score *= cat_w

            if query_emb:
                mem_emb = parse_embedding(getattr(m, "embedding_json", None))
                if mem_emb:
                    sim = cosine_similarity(query_emb, mem_emb)
                    base_score += sim * 0.5

            foresight = getattr(m, "foresight_json", None)
            if foresight and query_text:
                try:
                    fs_text = foresight if isinstance(foresight, str) else json.dumps(foresight)
                    overlap = sum(1 for w in query_text if w in fs_text)
                    if overlap > 2:
                        base_score += 0.15
                except Exception:
                    pass

            scored.append((m, base_score))

        scored.sort(key=lambda x: x[1], reverse=True)

        top_keys = {m.key for m, _ in scored[:top_k]}
        bonus_ids: set[int] = set()
        for m, _ in scored[:top_k]:
            rk = getattr(m, "related_keys", None)
            if rk:
                try:
                    keys_list = json.loads(rk) if isinstance(rk, str) else rk
                    for k in keys_list:
                        if k not in top_keys:
                            for m2, _ in scored:
                                if m2.key == k and m2.id not in bonus_ids:
                                    bonus_ids.add(m2.id)
                except Exception:
                    pass

        top = scored[:top_k]
        if bonus_ids:
            for m, s in scored[top_k:]:
                if m.id in bonus_ids:
                    top.append((m, s))
                    if len(top) >= top_k + 5:
                        break

        accessed_ids = [m.id for m, _ in top]
        await crud.increment_memory_access(self.db, accessed_ids)

        sections: dict[str, list[str]] = {
            "episodic": [],
            "semantic": [],
            "procedural": [],
            "preference": [],
            "medium": [],
            "long": [],
        }

        for m, score in top:
            cat = m.category
            val = _safe_json_load(m.value_json)
            episode_hint = ""
            ep = getattr(m, "episode", None)
            if ep:
                episode_hint = f" _[来源: {ep[:40]}]_"
            line = f"- **{m.key}**: {val}{episode_hint} _(score: {score:.2f})_"
            if cat in sections:
                sections[cat].append(line)
            else:
                sections.setdefault("other", []).append(line)

        lines: list[str] = [f"\n> 任务类型检测: {task_type}"]
        labels = {
            "episodic": "对话历史摘要",
            "semantic": "客观事实",
            "procedural": "决策模式",
            "preference": "个人偏好",
            "medium": "近期对话摘要（旧格式）",
            "long": "关键事实（旧格式）",
        }
        for cat, label in labels.items():
            items = sections.get(cat, [])
            if items:
                lines.append(f"\n## {label}")
                lines.extend(items)

        return "\n".join(lines) if len(lines) > 1 else ""

    async def process_after_conversation(
        self, new_messages: list[dict]
    ) -> None:
        total = await crud.count_conversations(self.db, self.project_id)

        if total > 0 and total % settings.memory_summary_threshold == 0:
            recent = await crud.get_recent_conversations(
                self.db, self.project_id, settings.memory_summary_threshold
            )
            msgs = [{"role": c.role, "content": c.content} for c in recent]

            try:
                segments = await segment_conversation(msgs)
                for seg in segments:
                    topic = seg.get("topic", "对话")
                    summary = seg.get("summary", "")
                    imp = float(seg.get("importance", 0.7))
                    key = f"episode_{total}_{topic.replace(' ', '_')[:30]}"
                    await crud.save_memory(
                        self.db,
                        self.project_id,
                        "episodic",
                        key,
                        summary,
                        importance=imp,
                        source="topic_segment",
                    )
            except Exception:
                logger.debug("Topic segmentation failed, falling back to summarizer", exc_info=True)
                summary = await summarize_conversations(msgs)
                await crud.save_memory(
                    self.db,
                    self.project_id,
                    "episodic",
                    f"summary_{total}",
                    summary,
                    importance=0.8,
                    source="conversation",
                )

        if new_messages:
            existing = await self._get_existing_facts()
            actions = await extract_facts(new_messages, existing)
            for item in actions:
                action = item.get("action", "ADD")
                category = item.get("category", "semantic")
                if category not in ("semantic", "procedural", "preference"):
                    category = "semantic"
                mem = await crud.upsert_memory(
                    self.db,
                    self.project_id,
                    action=action,
                    category=category,
                    key=item["key"],
                    value=item.get("value", ""),
                    importance=float(item.get("importance", 0.7)),
                    source="conversation",
                )
                if mem and action in ("ADD", "UPDATE"):
                    mem.episode = item.get("episode", "")
                    foresight = item.get("foresight")
                    if foresight:
                        mem.foresight_json = json.dumps(
                            foresight, ensure_ascii=False
                        ) if not isinstance(foresight, str) else foresight
                    related = item.get("related_keys")
                    if related and isinstance(related, list):
                        mem.related_keys = json.dumps(
                            related, ensure_ascii=False
                        )
                    await self.db.commit()
                    await self._embed_memory(mem)

    async def _get_existing_facts(self) -> list[dict]:
        mems = await crud.load_memories(self.db, self.project_id)
        return [
            {
                "key": m.key,
                "value": _safe_json_load(m.value_json),
                "category": m.category,
            }
            for m in mems
            if m.category in ("long", "semantic", "procedural", "preference")
        ]

    async def _embed_memory(self, mem: Memory) -> None:
        try:
            text = f"{mem.key}: {_safe_json_load(mem.value_json)}"
            emb = await get_embedding(text)
            if emb:
                mem.embedding_json = json.dumps(emb)
                await self.db.commit()
        except Exception:
            logger.debug("Failed to embed memory %s", mem.id, exc_info=True)

    async def save(
        self,
        category: str,
        key: str,
        value: object,
        importance: float = 1.0,
        source: str = "conversation",
    ) -> Memory:
        return await crud.save_memory(
            self.db,
            self.project_id, category, key, value, importance,
            source=source,
        )

    async def load(self, category: Optional[str] = None) -> list[dict]:
        mems = await crud.load_memories(self.db, self.project_id, category)
        return [self._mem_to_dict(m) for m in mems]

    @staticmethod
    def _mem_to_dict(m: Memory) -> dict:
        related = getattr(m, "related_keys", None)
        try:
            related_parsed = json.loads(related) if related else []
        except Exception:
            related_parsed = []
        return {
            "id": m.id,
            "category": m.category,
            "key": m.key,
            "value": _safe_json_load(m.value_json),
            "importance": m.importance_score,
            "source": getattr(m, "source", "conversation"),
            "access_count": getattr(m, "access_count", 0),
            "episode": getattr(m, "episode", None),
            "foresight": getattr(m, "foresight_json", None),
            "related_keys": related_parsed,
            "archived": bool(getattr(m, "archived", False)),
            "last_accessed_at": (
                m.last_accessed_at.isoformat()
                if getattr(m, "last_accessed_at", None)
                else None
            ),
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }

    async def load_all(self, include_archived: bool = False) -> list[dict]:
        mems = await crud.load_all_memories_for_project(
            self.db, self.project_id, include_archived
        )
        return [self._mem_to_dict(m) for m in mems]

"""
mem0-style fact extractor for research projects.
"""
import json
import logging

from agents.kimi_anthropic import chat_text

logger = logging.getLogger(__name__)

_SYSTEM = """你是深度研究助手的长期记忆管理模块（MemCell 架构）。
从对话中提取对后续研究、写作与决策有持久价值的结构化事实，并与已有记忆比对。

已有记忆以列表提供。你需要决定：
- **ADD**: 全新事实，已有记忆中没有
- **UPDATE**: 同一 key 的信息发生变化
- **DELETE**: 对话明确否定或撤回某条记忆
- **NOOP**: 已存在且无变化（不要输出 NOOP 条目）

输出 JSON（只输出 JSON）：
{
  "actions": [
    {
      "action": "ADD|UPDATE|DELETE",
      "key": "唯一键（英文下划线，如 research_question / key_paper / method_bias）",
      "value": "事实内容（简洁中文）",
      "category": "semantic|procedural|preference",
      "importance": 0.0~1.0,
      "episode": "产生该事实的对话片段摘要（一句话）",
      "foresight": "未来何种场景下最可能被检索（可选）",
      "related_keys": ["关联的其他 key"]
    }
  ]
}

分类：
- semantic: 客观事实（定义、数据、文献结论、实体关系等）
- procedural: 研究方法与流程偏好（检索策略、验证习惯、写作结构偏好）
- preference: 明确偏好（关注领域、排除来源、语气与深度）

规则：
1. 只提取明确信息，不猜测
2. DELETE 仅用于明确撤回
3. UPDATE 用于同一 key 的值变化
4. 无操作则 {"actions": []}
5. episode 必填；foresight、related_keys 可选"""


async def extract_facts(
    messages: list[dict],
    existing_memories: list[dict] | None = None,
) -> list[dict]:
    conversation_text = "\n".join(
        f"[{m['role']}]: {m['content']}" for m in messages
    )

    user_content = f"请分析以下对话并管理记忆：\n\n{conversation_text}"

    if existing_memories:
        mem_text = "\n".join(
            f"- [{m.get('category', 'semantic')}] {m['key']}: {m['value']}"
            for m in existing_memories
        )
        user_content += f"\n\n--- 已有记忆 ---\n{mem_text}"
    else:
        user_content += "\n\n--- 已有记忆 ---\n（暂无）"

    raw = await chat_text(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1024,
        temperature=0.2,
        timeout=60,
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("fact_extractor: malformed LLM JSON, returning empty actions. raw=%s err=%s", raw[:200], exc)
        return []
    if not isinstance(parsed, dict):
        logger.warning("fact_extractor: LLM returned non-dict top-level, ignoring")
        return []
    return parsed.get("actions", [])

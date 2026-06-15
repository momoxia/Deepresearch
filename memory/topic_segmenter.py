"""
Topic-boundary segmentation for episodic summaries.
"""
import json
import logging

from agents.kimi_anthropic import chat_text

logger = logging.getLogger(__name__)

_SYSTEM = """你是一个对话话题分段器。给定一段研究助手与用户的对话，你需要：
1. 判断是否存在话题转换（例如从「文献检索」到「方法讨论」）
2. 为每个话题段落生成一句话摘要
3. 标注段落边界（起止消息索引）

输出 JSON（只输出 JSON）：
{
  "segments": [
    {
      "start_idx": 0,
      "end_idx": 3,
      "topic": "话题关键词",
      "summary": "该段一句话摘要",
      "importance": 0.0~1.0
    }
  ]
}

规则：
- 单一话题时返回一个 segment
- summary 不超过 100 字
- topic 用 2-4 个关键词
- importance 按对后续研究/写作的价值评分"""


async def segment_conversation(messages: list[dict]) -> list[dict]:
    if len(messages) < 3:
        return [{
            "start_idx": 0,
            "end_idx": len(messages) - 1,
            "topic": "对话",
            "summary": messages[0]["content"][:100] if messages else "",
            "importance": 0.5,
        }]

    conversation_text = "\n".join(
        f"[{i}][{m['role']}]: {m['content']}" for i, m in enumerate(messages)
    )

    try:
        raw = await chat_text(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": f"请分析以下对话的话题边界：\n\n{conversation_text}",
                },
            ],
            max_tokens=1024,
            temperature=0.2,
            timeout=60,
        )
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        return parsed.get("segments", [])
    except Exception:
        logger.warning("Topic segmentation failed, falling back to single segment", exc_info=True)
        return [{
            "start_idx": 0,
            "end_idx": len(messages) - 1,
            "topic": "对话",
            "summary": messages[0]["content"][:100] if messages else "",
            "importance": 0.5,
        }]

"""
Compress recent dialogue into episodic summary via Kimi Anthropic-compatible API.
"""

from agents.kimi_anthropic import chat_text

_SYSTEM = """你是深度研究助手的记忆管理模块。
将以下对话压缩成一段简洁摘要（不超过300字），只保留对后续检索、写作与验证有价值的信息：
- 研究问题、假设、结论与争议点
- 关键文献、数据、定义与引用线索
- 待办与待验证项
不要保留无关闲聊。用中文输出。"""


async def summarize_conversations(messages: list[dict]) -> str:
    conversation_text = "\n".join(
        f"[{m['role']}]: {m['content']}" for m in messages
    )

    return await chat_text(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"请摘要以下对话：\n\n{conversation_text}"},
        ],
        max_tokens=512,
        temperature=0.2,
        timeout=60,
    )

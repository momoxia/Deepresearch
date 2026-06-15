"""
Auto-generate short session titles.
"""
import logging

from agents.kimi_anthropic import chat_text

logger = logging.getLogger(__name__)

_SYSTEM = """根据用户的第一条消息（以及助手的回复），生成简短对话标题。
要求：
- 不超过 15 个汉字（或等长英文）
- 概括研究或讨论主题
- 不要引号或多余标点
- 只输出标题文本"""


async def generate_title(user_message: str, assistant_reply: str = "") -> str:
    content = f"用户消息：{user_message[:500]}"
    if assistant_reply:
        content += f"\n助手回复：{assistant_reply[:300]}"

    try:
        title = await chat_text(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": content},
            ],
            max_tokens=64,
            temperature=0.3,
            timeout=30,
        )
        title = title.strip('"\'""''')
        return title[:50]
    except Exception:
        logger.warning("Title generation failed, using fallback", exc_info=True)
        return user_message[:20] + ("..." if len(user_message) > 20 else "")

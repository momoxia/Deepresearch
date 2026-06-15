"""
Agent helpers: prompts dir, time block, ClaudeAgentOptions builder.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from agents.mcp_registry import research_mcp_server

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_CST = timezone(timedelta(hours=8))

_WEEKDAY_ZH = ("一", "二", "三", "四", "五", "六", "日")


def current_time_block() -> str:
    now = datetime.now(_CST)
    weekday = f"星期{_WEEKDAY_ZH[now.weekday()]}"
    return (
        f"# 当前时间（系统权威信息，必须采信）\n\n"
        f"现在是北京时间 **{now.strftime('%Y年%m月%d日')} {weekday} {now.strftime('%H:%M')}**（UTC+8）。\n"
        f"这是服务器系统时钟给出的真实当前时间，是确定的事实，不是假设、演练或模板占位。\n\n"
        f"**关于日期的硬性规则：**\n"
        f"1. 你的训练数据截止于更早的年份，会让你\"凭直觉\"以为现在是更早的年份——这是错的。一律以上面的当前时间为准。\n"
        f"2. 搜索结果、网页、论文里的日期普遍早于今天属于正常现象（它们是较旧的内容），"
        f"这绝不意味着今天的日期错了。永远不要根据搜索结果或你的固有知识反推\"现在是哪一年\"。\n"
        f"3. 不要质疑、不要\"纠正\"、也不要向用户表示今天的日期看起来不对；任何时间问题都以本节为唯一事实来源。\n\n"
        f"**时效性提示（与上面的当前日期无关）**: 检索与引用时优先使用接近今天的来源，并在结论中标注来源时间与不确定性。"
    )


def load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


def build_options(
    system_prompt: str,
    allowed_tools: list[str],
    agents: dict | None = None,
    memory_context: str = "",
) -> ClaudeAgentOptions:
    time_block = current_time_block()
    full_prompt = f"{time_block}\n---\n\n{system_prompt}"
    if memory_context:
        full_prompt += f"\n\n---\n\n# 当前项目历史记忆\n\n{memory_context}"

    kwargs: dict = {
        "system_prompt": full_prompt,
        "allowed_tools": allowed_tools,
        "mcp_servers": {"research-tools": research_mcp_server},
        "permission_mode": "bypassPermissions",
    }
    if agents:
        kwargs["agents"] = agents

    return ClaudeAgentOptions(**kwargs)

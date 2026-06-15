"""
Single deep-research orchestrator: web tools + memory, no sub-agents.
"""
import re
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from agents.base import current_time_block, load_prompt
from agents.mcp_registry import TOOLS_ORCHESTRATOR, research_mcp_server


def _build_options(memory_context: str, project_id: int) -> ClaudeAgentOptions:
    time_block = current_time_block()
    base = load_prompt("deep_research.md")
    full_system = f"""
    {time_block}
    ---\n\n
    {base}
    ---\n\n
    # 运行上下文\n\n
   当前 **project_id** = `{project_id}`。\n
   调用 `load_memory` / `save_memory` 时必须传入该整数 `project_id`。\n
    """
    if memory_context:
        full_system += f"\n---\n\n# 当前项目历史记忆（检索摘要）\n\n{memory_context}"

    return ClaudeAgentOptions(
        system_prompt=full_system,
        allowed_tools=TOOLS_ORCHESTRATOR,
        mcp_servers={"research-tools": research_mcp_server},
        permission_mode="bypassPermissions",
        max_turns=30,
    )


async def run_chat(
    message: str,
    session_id: str | None,
    memory_context: str,
    project_id: int,
) -> tuple[str, str | None]:
    options = _build_options(memory_context, project_id)
    if session_id:
        options.resume = session_id  # type: ignore[attr-defined]

    new_session_id: str | None = None
    reply = ""

    async for msg in query(prompt=message, options=options):
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            new_session_id = msg.data.get("session_id")
        elif isinstance(msg, ResultMessage):
            reply = msg.result or ""

    return reply, new_session_id or session_id


_TOOL_LABELS: dict[str, str] = {
    "mcp__research-tools__web_search": "搜索",
    "mcp__research-tools__web_search_scholar": "学术搜索",
    "mcp__research-tools__web_fetch": "抓取网页",
    "mcp__research-tools__web_search_and_fetch": "搜索并抓取",
    "mcp__research-tools__pdf_parse": "解析 PDF",
    "mcp__research-tools__pdf_read": "PDF 精读",
    "mcp__research-tools__pdf_grep": "PDF 检索",
    "mcp__research-tools__pdf_vision": "PDF 读图",
    "mcp__research-tools__load_memory": "加载记忆",
    "mcp__research-tools__save_memory": "保存记忆",
    "mcp__research-tools__generate_artifact": "生成可视化",
}


_ARTIFACT_ID_RE = re.compile(r"artifact_id:\s*([a-f0-9]{6,})")


async def run_chat_stream(
    message: str,
    session_id: str | None,
    memory_context: str,
    project_id: int,
) -> AsyncIterator[dict[str, Any]]:
    options = _build_options(memory_context, project_id)
    if session_id:
        options.resume = session_id

    new_session_id: str | None = None
    reply = ""
    sources: list[dict[str, str]] = []
    pending_tool_ids: dict[str, str] = {}

    yield {"type": "status", "text": "正在分析您的问题..."}

    async for msg in query(prompt=message, options=options):
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            new_session_id = msg.data.get("session_id")
            yield {"type": "session", "session_id": new_session_id}
            continue

        if isinstance(msg, TaskStartedMessage):
            yield {
                "type": "task_start",
                "task_id": msg.task_id,
                "description": msg.description,
            }
            continue
        if isinstance(msg, TaskProgressMessage):
            yield {
                "type": "task_progress",
                "task_id": msg.task_id,
                "description": msg.description,
                "last_tool": msg.last_tool_name,
            }
            continue
        if isinstance(msg, TaskNotificationMessage):
            yield {
                "type": "task_done",
                "task_id": msg.task_id,
                "status": msg.status,
                "summary": msg.summary or "",
            }
            continue

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    label = _TOOL_LABELS.get(tool_name, tool_name)
                    pending_tool_ids[block.id] = tool_name
                    yield {
                        "type": "tool_start",
                        "tool": tool_name,
                        "label": label,
                        "input": _safe_input_summary(tool_name, block.input),
                    }
                    _collect_source(tool_name, block.input, sources)
                elif isinstance(block, TextBlock) and block.text.strip():
                    yield {"type": "text", "content": block.text}
            continue

        if isinstance(msg, UserMessage):
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    tool_name = pending_tool_ids.pop(block.tool_use_id, "")
                    result_text = _extract_tool_result_text(block)
                    if result_text and tool_name:
                        yield {
                            "type": "tool_result",
                            "tool": tool_name,
                            "tool_use_id": block.tool_use_id,
                            "result": result_text,
                        }
                        if "generate_artifact" in tool_name:
                            m = _ARTIFACT_ID_RE.search(result_text)
                            if m:
                                artifact_id = m.group(1)
                                yield {
                                    "type": "artifact",
                                    "artifact_id": artifact_id,
                                    "preview_url": f"/artifacts/{artifact_id}",
                                }
            continue

        if isinstance(msg, ResultMessage):
            reply = msg.result or ""
            continue

    final_session = new_session_id or session_id
    yield {
        "type": "done",
        "session_id": final_session,
        "reply": reply,
        "sources": sources,
    }


def _extract_tool_result_text(block: ToolResultBlock) -> str:
    if isinstance(block.content, str):
        return block.content
    if isinstance(block.content, list):
        parts = []
        for item in block.content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, TextBlock):
                parts.append(item.text)
        return "\n".join(parts)
    return str(block.content)[:300] if block.content else ""


def _safe_input_summary(tool_name: str, tool_input: dict) -> dict:
    if "web_search_and_fetch" in tool_name:
        return {"query": tool_input.get("query", ""), "num": tool_input.get("num_results", 5)}
    if "web_search_scholar" in tool_name:
        return {"query": tool_input.get("query", "")}
    if "web_search" in tool_name:
        return {"query": tool_input.get("query", "")}
    if "pdf_parse" in tool_name:
        return {"url": tool_input.get("url", "")}
    if "pdf_read" in tool_name:
        return {
            "doc_id": (tool_input.get("doc_id") or "")[:24],
            "offset": tool_input.get("offset", 0),
            "limit": tool_input.get("limit", 6000),
        }
    if "pdf_grep" in tool_name:
        pat = tool_input.get("pattern") or ""
        return {
            "doc_id": (tool_input.get("doc_id") or "")[:24],
            "pattern": pat[:80] + ("…" if len(pat) > 80 else ""),
        }
    if "pdf_vision" in tool_name:
        q = tool_input.get("question") or ""
        return {
            "doc_id": (tool_input.get("doc_id") or "")[:24],
            "query": q[:100] + ("…" if len(q) > 100 else ""),
        }
    if "web_fetch" in tool_name:
        return {"url": tool_input.get("url", "")}
    if "load_memory" in tool_name or "save_memory" in tool_name:
        return {
            "project_id": tool_input.get("project_id", ""),
            "category": tool_input.get("category", ""),
            "key": (tool_input.get("key") or "")[:80],
        }
    return {"summary": str(tool_input)[:100]}


def _collect_source(tool_name: str, tool_input: dict, sources: list[dict[str, str]]):
    if "pdf_parse" in tool_name:
        url = tool_input.get("url", "")
        if url and not any(s["url"] == url for s in sources):
            sources.append({"url": url, "title": f"PDF: {url.rsplit('/', 1)[-1][:50]}"})
        return
    if "web_fetch" in tool_name:
        url = tool_input.get("url", "")
        if url and not any(s["url"] == url for s in sources):
            sources.append({"url": url, "title": url.split("/")[2] if "/" in url else url})
    elif "web_search_scholar" in tool_name:
        q = tool_input.get("query", "")
        if q:
            sources.append({
                "url": f"https://scholar.google.com/scholar?q={q}",
                "title": f"学术搜索: {q[:40]}",
            })
    elif "web_search" in tool_name:
        q = tool_input.get("query", "")
        if q:
            sources.append({
                "url": f"https://google.com/search?q={q}",
                "title": f"搜索: {q[:40]}",
            })

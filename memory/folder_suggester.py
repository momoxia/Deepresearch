"""
Generate a folder tree proposal from all projects + user instruction.
"""
import json
import logging
import re

from agents.kimi_anthropic import chat_text

logger = logging.getLogger(__name__)

_SYSTEM = """你是一个对话整理助手。根据用户的整理要求，为给定的一批对话生成文件夹树，并把每个对话分配到合适的叶节点。

每个对话会附带长期记忆画像（语义/程序/偏好记忆 + 情景摘要），这些是该项目历史沉淀下来的事实、研究主题、方法论与用户偏好，请优先据此判断主题类别，而不是只看首句。

严格输出一个 JSON 对象，结构如下（不要包裹代码块、不要加解释）：
{
  "folders": [
    {"tmp_id": "f1", "name": "...", "parent_tmp_id": null, "sort_order": 0}
  ],
  "assignments": [
    {"project_id": 12, "folder_tmp_id": "f1"}
  ],
  "rationale": "一句话说明分类逻辑"
}

规则：
- tmp_id 使用 f1/f2/... 这样的临时字符串
- parent_tmp_id 用于多级嵌套；顶层写 null
- 不要创建空文件夹；每个文件夹至少有一个对话
- 文件夹名简短（不超过 10 个汉字），体现主题
- assignments 必须覆盖传入的所有 project_id，若无法归类则 folder_tmp_id 设为 null
- 层级不要超过 3 层
- 当某个对话的记忆画像与其它对话高度重叠，优先合并进同一文件夹"""


def _format_profile(p: dict) -> str:
    title = p.get("title") or p.get("name") or ""
    snippet = (p.get("snippet") or "").strip()
    lines = [f'- id={p["id"]} 标题="{title}"']
    if snippet:
        lines.append(f"  首句：{snippet}")

    semantic = p.get("semantic") or []
    if semantic:
        items = "；".join(f"{m['key']}={m['value']}" for m in semantic if m.get("value"))
        if items:
            lines.append(f"  语义记忆：{items}")

    procedural = p.get("procedural") or []
    if procedural:
        items = "；".join(f"{m['key']}={m['value']}" for m in procedural if m.get("value"))
        if items:
            lines.append(f"  方法论：{items}")

    preference = p.get("preference") or []
    if preference:
        items = "；".join(f"{m['key']}={m['value']}" for m in preference if m.get("value"))
        if items:
            lines.append(f"  偏好：{items}")

    episode = (p.get("episode_brief") or "").strip()
    if episode:
        lines.append(f"  情景摘要：{episode}")

    count = p.get("memory_count")
    if count is not None and not (semantic or procedural or preference or episode):
        lines.append(f"  （记忆 {count} 条）")

    return "\n".join(lines)


async def suggest_folder_tree(
    instruction: str,
    projects: list[dict],
) -> dict:
    """
    projects: enriched profiles with keys:
      id, name, title, snippet, semantic[], procedural[], preference[], episode_brief, memory_count
    Returns: {"folders": [...], "assignments": [...], "rationale": str}
    """
    proj_block = "\n".join(_format_profile(p) for p in projects) if projects else "（无对话）"

    user_content = (
        f"整理要求：{instruction}\n\n"
        f"共 {len(projects)} 个对话：\n{proj_block}\n\n"
        "请输出分类 JSON。"
    )

    raw = await chat_text(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=2048,
        temperature=0.3,
        timeout=90,
    )
    parsed = _extract_json(raw)
    if not parsed:
        raise ValueError(f"LLM 返回无法解析为 JSON: {raw[:200]}")

    parsed.setdefault("folders", [])
    parsed.setdefault("assignments", [])
    parsed.setdefault("rationale", "")
    return parsed


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None

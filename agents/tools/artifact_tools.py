"""
Artifact generator — mini-swe-agent 风格。

直接调 Kimi Anthropic-compat `/v1/messages`,让模型一次性输出一个 ```jsx 代码块。
失败时把 esbuild / 安全校验 stderr 拼到下一轮 user message 回灌(linear history)。
无 agent loop、无 tool_use、无 CLI 子进程。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import uuid
from pathlib import Path

import httpx
from claude_agent_sdk import tool

from config import settings
from db.database import AsyncSessionLocal
from db import crud

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ESBUILD_BIN = _REPO_ROOT / "node_modules" / ".bin" / "esbuild"

FORBIDDEN_KEYWORDS = [
    "localStorage",
    "sessionStorage",
    "document.cookie",
    "window.location",
    "XMLHttpRequest",
    "fetch(",
    "import(",
]

_ALLOWED_DEPS = ("react", "recharts", "lucide-react")

_MAX_RETRIES = 5
_COMPILE_TIMEOUT_SEC = 30
# 关掉 reasoning 后单次 10-30s 就够;留 2 分钟余量应对偶发长响应
_CHAT_TIMEOUT_SEC = 300
_GENERATE_TIMEOUT_SEC = 900

SYSTEM_PROMPT = """你是 React artifact 生成器。根据研究内容,输出单文件可交互 React 组件。

## 硬约束(违反 → 渲染失败)
1. 只能 import:`react`、`recharts`、`lucide-react`(不得 import 其他任何模块)
2. 样式用 inline style 对象;禁用 Tailwind / CSS modules / 外链 CSS
3. 禁止 `localStorage` / `sessionStorage` / `fetch` / `XMLHttpRequest` / 动态 `import()`
4. 单文件,默认导出函数组件:`export default function ...`
5. 所有数据**内联**在组件里,不依赖 props / URL / API

## 设计要求
- **必须撑满容器**:根组件不要写 `maxWidth` / 固定 `width`,用 `width: '100%'` + 内边距;不要 `margin: '0 auto'` 居中后留大片空白
- 响应式单列;基础字号 ≥14px,关键数字 ≥20px
- 至少一个可交互元素(按钮 / 滑块 / tab / 步进器)
- 深色背景、高对比度(body 会被宿主设为 `#0c0a09`,组件背景尽量和它融合或直接透明)
- 避免俗套的紫色渐变 / Inter 字体 / 统一卡片网格

## 输出格式(严格遵守)
**只回复一个 ```jsx 代码块**,不要任何其他文字、解释、Markdown 标题、思考过程。
代码块以 ```jsx 开始,以 ``` 结束,中间是完整可运行的 React 组件源码。
"""


def _check_forbidden(code: str) -> tuple[bool, str]:
    for kw in FORBIDDEN_KEYWORDS:
        if kw in code:
            return False, f"代码包含禁用关键字: {kw}"

    for match in re.finditer(r"^\s*import\s+[^;]+?from\s+['\"]([^'\"]+)['\"]", code, re.MULTILINE):
        mod = match.group(1)
        if not any(mod == dep or mod.startswith(dep + "/") for dep in _ALLOWED_DEPS):
            return False, f"禁止 import 非白名单模块: {mod}(只允许 {', '.join(_ALLOWED_DEPS)})"
    return True, "ok"


def _compile_check(jsx_path: Path) -> tuple[bool, str]:
    if not _ESBUILD_BIN.exists():
        return False, f"esbuild 不存在: {_ESBUILD_BIN}。请在仓库根目录运行 `npm install --save-dev esbuild`。"
    try:
        result = subprocess.run(
            [
                str(_ESBUILD_BIN),
                str(jsx_path),
                "--bundle",
                "--loader:.jsx=jsx",
                "--external:react",
                "--external:recharts",
                "--external:lucide-react",
                "--outfile=/tmp/_artifact_check.js",
            ],
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, f"esbuild 编译超时(>{_COMPILE_TIMEOUT_SEC}s)"

    if result.returncode != 0:
        return False, (result.stderr or "compile failed")[:1500]
    return True, "ok"


def _kimi_messages_url() -> str:
    return f"{settings.anthropic_base_url.rstrip('/')}/v1/messages"


async def _kimi_chat(messages: list[dict]) -> str:
    """
    调 Kimi Anthropic-compat `/v1/messages`,**显式关闭 thinking** 降低延迟。
    k2.6 默认开 reasoning,单次可到 200s+,还经常触发上游 ALB 504;
    `thinking: {"type":"disabled"}` 之后单次回落到个位数秒。

    入参 messages 仍用 OpenAI 风格 [{role, content}],内部自动把 system 拆出来。
    """
    system_text = ""
    anthropic_messages: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_text = (system_text + "\n\n" + content).strip() if system_text else content
        else:
            anthropic_messages.append({"role": role, "content": content})

    payload: dict = {
        "model": settings.anthropic_model,
        "max_tokens": 16000,
        "thinking": {"type": "disabled"},
        "messages": anthropic_messages,
    }
    if system_text:
        payload["system"] = system_text

    headers = {
        "x-api-key": settings.anthropic_auth_token,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT_SEC, trust_env=False) as client:
        resp = await client.post(_kimi_messages_url(), json=payload, headers=headers)
        if resp.status_code >= 400:
            body_preview = resp.text[:1500]
            raise RuntimeError(
                f"Kimi API HTTP {resp.status_code}: {body_preview}"
            )
        data = resp.json()

    # Anthropic 响应:content 是 [{type:"text", text:"..."}, ...]
    blocks = data.get("content") or []
    texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(texts)


_JSX_BLOCK_RE = re.compile(r"```(?:jsx|javascript|js|tsx)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


def _extract_jsx(text: str) -> str | None:
    m = _JSX_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    t = text.strip()
    if t.startswith("import ") and "export default" in t:
        return t
    return None


def _dump(work_dir: Path, attempt: int, messages: list[dict], response_text: str) -> None:
    try:
        (work_dir / f"request.attempt{attempt}.json").write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        logger.exception("写入 request.json 失败")
    try:
        (work_dir / f"response.attempt{attempt}.txt").write_text(
            response_text, encoding="utf-8"
        )
    except Exception:
        logger.exception("写入 response.txt 失败")


async def _generate(
    research_content: str,
    viz_hint: str,
    project_id: int,
    title: str | None,
    session_id: str | None,
) -> dict:
    artifact_id = uuid.uuid4().hex[:10]
    work_dir = ARTIFACT_DIR / artifact_id
    work_dir.mkdir(parents=True, exist_ok=True)
    jsx_path = work_dir / "App.jsx"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"研究内容:\n{research_content}\n\n"
                f"可视化提示: {viz_hint or '自由发挥'}\n\n"
                f"请按系统约束输出一个 ```jsx 代码块。"
            ),
        },
    ]

    last_err: str | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            content = await _kimi_chat(messages)
        except Exception as exc:
            logger.exception("Kimi chat failed on attempt %d", attempt)
            # 某些 httpx 异常(如 ReadTimeout)str()为空,显式带类型名便于诊断
            exc_desc = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            last_err = f"Kimi API 请求失败: {exc_desc}"
            try:
                (work_dir / f"error.attempt{attempt}.txt").write_text(
                    exc_desc, encoding="utf-8"
                )
            except Exception:
                logger.exception("写入 error.txt 失败")
            messages.append({
                "role": "user",
                "content": f"上一轮请求失败: {last_err}\n请重新输出完整的 ```jsx 代码块。",
            })
            continue

        _dump(work_dir, attempt, messages, content)

        code = _extract_jsx(content)
        if code is None:
            last_err = "输出里没找到 ```jsx 代码块,或代码块不完整。"
        else:
            jsx_path.write_text(code, encoding="utf-8")
            ok, err = _check_forbidden(code)
            if not ok:
                last_err = err
            else:
                ok, err = _compile_check(jsx_path)
                if not ok:
                    last_err = f"esbuild 编译失败:\n{err}"
                else:
                    async with AsyncSessionLocal() as db:
                        await crud.create_artifact(
                            db,
                            artifact_id=artifact_id,
                            project_id=project_id,
                            code=code,
                            session_id=session_id,
                            title=title,
                            viz_hint=viz_hint or None,
                            research_content=research_content[:4000],
                        )
                    return {
                        "artifact_id": artifact_id,
                        "preview_url": f"/artifacts/{artifact_id}",
                        "attempts": attempt,
                    }

        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": (
                f"<validation_error attempt={attempt}>\n"
                f"上一轮失败:\n{last_err}\n"
                f"请修复后重新输出**完整**的 ```jsx 代码块,不要输出 diff,不要任何解释文字。\n"
                f"</validation_error>"
            ),
        })

    raise RuntimeError(
        f"artifact 生成失败,{_MAX_RETRIES} 次重试仍未通过校验。最后错误: {last_err}"
    )


@tool(
    "generate_artifact",
    (
        "生成一个可交互的 React artifact(单文件组件)用于可视化研究结论。"
        "**调用时机**:当研究结论涉及算法流程、数据对比、架构示意、可步进过程等"
        "**适合可视化**的内容时调用;纯文字答案或单一数值结果**不要**调用。"
        "生成成功后会返回 artifact_id,请在最终回复中告知用户可以通过界面查看。"
    ),
    {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "integer",
                "description": "当前研究项目 ID(从系统 prompt 的运行上下文获取)",
            },
            "research_content": {
                "type": "string",
                "description": "需要可视化的完整研究结论,尽量详细。包含关键数据、步骤、对象名称等。",
            },
            "viz_hint": {
                "type": "string",
                "description": "可选的可视化方向提示,例如 '步进式流程图' / '数据对比卡片' / '交互式模拟器' / '时间线'",
            },
            "title": {
                "type": "string",
                "description": "可选:artifact 的简短标题(≤30 字),便于前端展示",
            },
        },
        "required": ["project_id", "research_content"],
    },
)
async def generate_artifact(args: dict) -> dict:
    project_id = int(args["project_id"])
    research_content = args["research_content"].strip()
    viz_hint = (args.get("viz_hint") or "").strip()
    title = (args.get("title") or "").strip() or None

    if not research_content:
        return {
            "content": [
                {"type": "text", "text": "❌ research_content 为空,无法生成 artifact。"}
            ],
            "is_error": True,
        }

    try:
        result = await asyncio.wait_for(
            _generate(
                research_content=research_content,
                viz_hint=viz_hint,
                project_id=project_id,
                title=title,
                session_id=None,
            ),
            timeout=_GENERATE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"❌ artifact 生成超时(>{_GENERATE_TIMEOUT_SEC}s)。",
                }
            ],
            "is_error": True,
        }
    except Exception as exc:
        logger.exception("generate_artifact failed")
        return {
            "content": [{"type": "text", "text": f"❌ artifact 生成失败: {exc}"}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"✅ artifact 已生成。\n"
                    f"artifact_id: {result['artifact_id']}\n"
                    f"preview_url: {result['preview_url']}\n"
                    f"attempts: {result['attempts']}\n\n"
                    f"请在最终回复中告诉用户已生成可视化,让前端渲染即可。"
                ),
            }
        ]
    }

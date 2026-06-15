"""
搜索与网页抓取 MCP 工具：
  - web_search:           Serper 普通搜索（支持 time_range）
  - web_search_scholar:   Serper Scholar 学术搜索
  - web_fetch:            单页抓取 + Kimi 总结（支持 research_context）
  - web_search_and_fetch: 搜索 + 并行抓取 + 并行总结（支持两者）
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx
from readability import Document
from markdownify import markdownify as md

from claude_agent_sdk import tool
from agents.kimi_anthropic import chat_text
from config import settings

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}

_SUMMARY_SYSTEM = (
    "你是一个网页内容提取助手。根据给出的网页正文，输出精简 Markdown 摘要（不超过800字）。\n"
    "优先保留可核验的事实：定义、数据、方法、结论、作者/机构、日期与引用线索；"
    "去掉广告、导航、版权声明等噪声。若页面与研究问题完全无关，用一两句话说明主题即可。"
)

# time_range -> Serper tbs 映射
_TIME_RANGE_MAP: dict[str, str] = {
    "day":   "qdr:d",
    "week":  "qdr:w",
    "month": "qdr:m",
    "year":  "qdr:y",
    "all":   "",
}


def _is_pdf_url(url: str) -> bool:
    """Heuristic: detect if a URL points to a PDF file."""
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _build_tbs(time_range: str) -> str | None:
    """将 time_range 字符串转为 Serper tbs 值；无效值默认 year。"""
    tbs = _TIME_RANGE_MAP.get(time_range.lower(), "qdr:y")
    return tbs if tbs else None


# ─── web_search ──────────────────────────────────────────────────────────────

@tool(
    "web_search",
    "通过 Serper.dev API 搜索 Google，返回结构化搜索结果（标题、URL、摘要）",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如 'transformer attention mechanism 2024'",
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果条数，默认3",
                "default": 3,
            },
            "gl": {
                "type": "string",
                "description": "地区代码，如 us、gb、cn，默认 us",
                "default": "us",
            },
            "time_range": {
                "type": "string",
                "description": "时间范围：day / week / month / year（默认）/ all（不限，适合历史/政策/经典文献）",
                "default": "year",
            },
        },
        "required": ["query"],
    },
)
async def web_search(args: dict) -> dict:
    query = args["query"]
    num = int(args.get("num_results", 3))
    gl = args.get("gl", "us")
    tbs = _build_tbs(args.get("time_range", "year"))

    if not settings.serper_api_key:
        return {"error": "SERPER_API_KEY 未配置，请在 .env 中设置。"}

    now = datetime.now(_CST)
    payload: dict = {"q": query, "gl": gl, "num": num}
    if tbs:
        payload["tbs"] = tbs
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    organic = data.get("organic", [])
    results = []
    for item in organic[:num]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "date": item.get("date", ""),
        })

    knowledge_graph = data.get("knowledgeGraph")
    kg_text = ""
    if knowledge_graph:
        kg_text = (
            f"\n\n**知识图谱**: {knowledge_graph.get('title', '')} — "
            f"{knowledge_graph.get('description', '')}"
        )

    timestamp = now.strftime("%Y-%m-%d %H:%M UTC+8")
    output = f"搜索 \"{query}\" 共获得 {len(results)} 条结果（搜索时间: {timestamp}）：\n\n"
    for i, r in enumerate(results, 1):
        date_tag = f" [{r['date']}]" if r["date"] else ""
        output += f"{i}. **{r['title']}**{date_tag}\n   {r['url']}\n   {r['snippet']}\n\n"
    output += kg_text

    return {
        "content": [{"type": "text", "text": output.strip()}]
    }


# ─── web_search_scholar ───────────────────────────────────────────────────────

@tool(
    "web_search_scholar",
    "通过 Serper Scholar 端点搜索学术论文（Google Scholar），返回标题、作者、引用数、摘要片段和 URL",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "学术搜索关键词，如 'BERT language model pretraining'",
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果条数，默认5",
                "default": 5,
            },
            "research_context": {
                "type": "string",
                "description": "当前研究问题的一句话描述，用于在摘要中聚焦相关内容（可选）",
            },
        },
        "required": ["query"],
    },
)
async def web_search_scholar(args: dict) -> dict:
    query = args["query"]
    num = int(args.get("num_results", 5))
    research_context = args.get("research_context", "")

    if not settings.serper_api_key:
        return {"error": "SERPER_API_KEY 未配置，请在 .env 中设置。"}

    now = datetime.now(_CST)
    payload: dict = {"q": query, "num": num}
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.post(
            "https://google.serper.dev/scholar",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    organic = data.get("organic", [])
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC+8")
    ctx_line = f"（研究问题：{research_context}）" if research_context else ""
    output = f"Scholar 搜索 \"{query}\" {ctx_line}共 {len(organic)} 条结果（{timestamp}）：\n\n"

    for i, item in enumerate(organic[:num], 1):
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")
        authors = item.get("publicationInfo", {}).get("authors", [])
        author_str = "、".join(a.get("name", "") for a in authors[:4]) if authors else ""
        cited_by = item.get("citedBy", {}).get("total", "")
        year = item.get("year", "")

        meta_parts = []
        if author_str:
            meta_parts.append(author_str)
        if year:
            meta_parts.append(str(year))
        if cited_by:
            meta_parts.append(f"被引 {cited_by} 次")
        meta = " · ".join(meta_parts)

        output += f"{i}. **{title}**\n"
        if meta:
            output += f"   {meta}\n"
        if link:
            output += f"   {link}\n"
        if snippet:
            output += f"   {snippet}\n"
        output += "\n"

    return {
        "content": [{"type": "text", "text": output.strip()}]
    }


# ─── web_fetch ────────────────────────────────────────────────────────────────

@tool(
    "web_fetch",
    "抓取指定 URL 的网页内容，提取正文并用 Kimi 生成精简摘要",
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标网页 URL",
            },
            "max_chars": {
                "type": "integer",
                "description": "正文截断字符数上限，默认4000",
                "default": 4000,
            },
            "research_context": {
                "type": "string",
                "description": "当前研究问题的一句话描述，帮助摘要模型聚焦相关内容（强烈建议传入）",
            },
        },
        "required": ["url"],
    },
)
async def web_fetch(args: dict) -> dict:
    url = args["url"]
    max_chars = int(args.get("max_chars", settings.web_fetch_max_chars))
    research_context = args.get("research_context", "")
    source_method = "httpx"

    if _is_pdf_url(url) and settings.pdf_parse_url:
        from agents.tools.pdf_tools import pdf_parse
        return await pdf_parse({
            "url": url,
            "research_context": research_context,
        })

    try:
        raw_html = await _fetch_html(url)
        markdown_text = _extract_markdown(raw_html, max_chars)
    except Exception:
        markdown_text = ""

    if len(markdown_text.strip()) < 50 and settings.firecrawl_api_key:
        try:
            markdown_text = await _fetch_with_firecrawl(url, max_chars)
            source_method = "firecrawl"
        except Exception:
            pass

    if len(markdown_text.strip()) < 50:
        return {
            "content": [{"type": "text", "text": f"页面 {url} 正文内容过少，可能是需要 JS 渲染的动态页面或被反爬拦截。"}]
        }

    try:
        summary = await _summarize_with_kimi(markdown_text, url, research_context)
    except Exception as e:
        summary = f"（总结失败: {e}）\n\n原文前2000字：\n{markdown_text[:2000]}"

    fetch_time = datetime.now(_CST).strftime("%Y-%m-%d %H:%M UTC+8")
    tag = f" [via {source_method}]" if source_method != "httpx" else ""
    return {
        "content": [{"type": "text", "text": f"**来源**: {url}{tag}\n**抓取时间**: {fetch_time}\n\n{summary}"}]
    }


def _fetch_html_sync(url: str) -> str:
    pass


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=settings.web_fetch_timeout,
        follow_redirects=True,
        trust_env=False,
        headers=_FETCH_HEADERS,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _sanitize_html(html: str) -> str:
    import re
    html = html.replace("\x00", "")
    html = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", html)
    return html


def _extract_markdown(html: str, max_chars: int) -> str:
    html = _sanitize_html(html)
    doc = Document(html)
    content_html = doc.summary()
    text = md(content_html, heading_style="ATX", strip=["img", "script", "style"])
    text = "\n".join(line for line in text.splitlines() if line.strip())
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n...(内容已截断)"
    return text


async def _summarize_with_kimi(
    text: str,
    source_url: str,
    research_context: str = "",
) -> str:
    system_prompt = _SUMMARY_SYSTEM
    if research_context:
        system_prompt += f"\n\n当前研究问题：「{research_context}」——请优先提取与此问题直接相关的内容。"

    return await chat_text(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"以下是来自 {source_url} 的网页正文：\n\n{text}"},
        ],
        max_tokens=1024,
        temperature=0.3,
        timeout=60,
    )


async def _fetch_with_firecrawl(url: str, max_chars: int) -> str:
    """使用 Firecrawl API 抓取需要 JS 渲染的页面，返回 Markdown 正文。"""
    headers = {
        "Authorization": f"Bearer {settings.firecrawl_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url,
        "formats": ["markdown"],
    }
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        resp = await client.post(
            "https://api.firecrawl.dev/v1/scrape",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    text = data.get("data", {}).get("markdown", "")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n...(内容已截断)"
    return text


# ─── Composite tool: search + parallel fetch + parallel summarize ────────────

async def _fetch_single_page(url: str, max_chars: int) -> dict:
    """Fetch a single page and return {url, markdown, method, error}."""
    markdown_text = ""
    method = "httpx"
    try:
        raw_html = await _fetch_html(url)
        markdown_text = _extract_markdown(raw_html, max_chars)
    except Exception:
        markdown_text = ""

    if len(markdown_text.strip()) < 50 and settings.firecrawl_api_key:
        try:
            markdown_text = await _fetch_with_firecrawl(url, max_chars)
            method = "firecrawl"
        except Exception:
            pass

    if len(markdown_text.strip()) < 50:
        return {"url": url, "markdown": "", "method": method, "error": "内容过少或被反爬拦截"}

    return {"url": url, "markdown": markdown_text, "method": method, "error": None}


async def _summarize_single(url: str, markdown: str, research_context: str = "") -> str:
    """Summarize a single page's markdown with Kimi."""
    try:
        return await _summarize_with_kimi(markdown, url, research_context)
    except Exception as e:
        return f"（总结失败: {e}）\n\n原文前1500字：\n{markdown[:1500]}"


@tool(
    "web_search_and_fetch",
    "一次性搜索+并行抓取所有结果+并行总结。适合明确的信息查询，比分开调用 web_search + web_fetch 快 3-5 倍。",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "num_results": {
                "type": "integer",
                "description": "搜索结果条数，默认5",
                "default": 5,
            },
            "gl": {
                "type": "string",
                "description": "地区代码，默认 us",
                "default": "us",
            },
            "time_range": {
                "type": "string",
                "description": "时间范围：day / week / month / year（默认）/ all",
                "default": "year",
            },
            "research_context": {
                "type": "string",
                "description": "当前研究问题的一句话描述，帮助摘要模型聚焦相关内容（强烈建议传入）",
            },
        },
        "required": ["query"],
    },
)
async def web_search_and_fetch(args: dict) -> dict:
    query = args["query"]
    num = int(args.get("num_results", 5))
    gl = args.get("gl", "us")
    tbs = _build_tbs(args.get("time_range", "year"))
    research_context = args.get("research_context", "")
    max_chars = settings.web_fetch_max_chars

    if not settings.serper_api_key:
        return {"error": "SERPER_API_KEY 未配置"}

    now = datetime.now(_CST)

    payload: dict = {"q": query, "gl": gl, "num": num}
    if tbs:
        payload["tbs"] = tbs
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        resp = await client.post(
            "https://google.serper.dev/search", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()

    organic = data.get("organic", [])
    search_results = []
    for item in organic[:num]:
        search_results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "date": item.get("date", ""),
        })

    if not search_results:
        return {"content": [{"type": "text", "text": f"搜索 \"{query}\" 无结果。"}]}

    urls = [r["url"] for r in search_results if r["url"]]

    fetch_tasks = [_fetch_single_page(url, max_chars) for url in urls]
    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    to_summarize = []
    for fr in fetch_results:
        if isinstance(fr, Exception):
            continue
        if fr.get("markdown") and not fr.get("error"):
            to_summarize.append(fr)

    summary_tasks = [
        _summarize_single(fr["url"], fr["markdown"], research_context)
        for fr in to_summarize
    ]
    summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)

    summary_map: dict[str, str] = {}
    for fr, s in zip(to_summarize, summaries):
        if isinstance(s, Exception):
            summary_map[fr["url"]] = f"（总结失败）\n{fr['markdown'][:1500]}"
        else:
            summary_map[fr["url"]] = s

    timestamp = now.strftime("%Y-%m-%d %H:%M UTC+8")
    fetch_time = datetime.now(_CST).strftime("%Y-%m-%d %H:%M UTC+8")
    elapsed_note = f"（搜索: {timestamp}，抓取完成: {fetch_time}）"

    output_parts = [
        f"## 搜索 \"{query}\" — {len(search_results)} 条结果，"
        f"成功抓取 {len(summary_map)} 页 {elapsed_note}\n"
    ]

    for i, r in enumerate(search_results, 1):
        url = r["url"]
        date_tag = f" [{r['date']}]" if r.get("date") else ""
        output_parts.append(f"### {i}. {r['title']}{date_tag}")
        output_parts.append(f"**URL**: {url}\n")

        if url in summary_map:
            output_parts.append(summary_map[url])
        else:
            fr_match = next(
                (fr for fr in fetch_results
                 if not isinstance(fr, Exception) and fr["url"] == url),
                None,
            )
            if fr_match and fr_match.get("error"):
                output_parts.append(f"_抓取失败: {fr_match['error']}_")
            else:
                output_parts.append(f"_{r['snippet']}_")

        output_parts.append("")

    kg = data.get("knowledgeGraph")
    if kg:
        output_parts.append(
            f"**知识图谱**: {kg.get('title', '')} — {kg.get('description', '')}"
        )

    return {
        "content": [{"type": "text", "text": "\n".join(output_parts).strip()}]
    }

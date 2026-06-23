"""
PDF 解析 MCP 工具（Hermes 风格：persist full, paginate, grep — no LLM 压缩）：
  - pdf_parse: 下载 PDF → MinerU 解析为 Markdown → **完整落盘** → 返回 doc_id + 预览 + 章节目录
  - pdf_read : 按 offset/limit 分页读取已缓存的 Markdown 原文
  - pdf_grep : 在已缓存的 Markdown 里做正则匹配，返回命中行 + 上下文（用于数值核实）
  - pdf_vision: 从缓存 Markdown 中提取 ![](...) 图片（同 MinerU 源站），用 Kimi Vision 回答「图里有什么」
"""
import base64
import hashlib
import io
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta

import httpx

from claude_agent_sdk import tool

from agents.multimodal.markdown_content import build_pdf_markdown_vision_parts, run_kimi_vision_chat
from config import settings

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _cache_root() -> str:
    root = settings.pdf_cache_dir
    os.makedirs(root, exist_ok=True)
    return root


def _doc_id_for_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _cache_path(doc_id: str) -> str:
    return os.path.join(_cache_root(), f"{doc_id}.md")


def _meta_path(doc_id: str) -> str:
    return os.path.join(_cache_root(), f"{doc_id}.meta")


def _load_cached_md(doc_id: str) -> str | None:
    path = _cache_path(doc_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_cache(doc_id: str, md_text: str, source_url: str, filename: str) -> None:
    with open(_cache_path(doc_id), "w", encoding="utf-8") as f:
        f.write(md_text)
    with open(_meta_path(doc_id), "w", encoding="utf-8") as f:
        f.write(f"source_url: {source_url}\nfilename: {filename}\nchars: {len(md_text)}\n")


# ── 图文混排：MinerU 导出的图片落盘 + 安全取图 ─────────────────────────────
# MinerU /file_parse 在 return_images=true 时返回 results[<pdf>]["images"] =
# { "<hash>.jpg": "data:image/jpeg;base64,..." }，key 对应 Markdown 里的
# ![](images/<hash>.jpg)。MinerU 本身不托管图片（直接 GET 会 404），所以必须
# 在解析时把 base64 解码落盘到 {doc_id}/images/，前端再经 /api/pdf-image 取本地文件。
# 官方 MinerU 的 RESULT_IMAGE_SUFFIXES = image_suffixes | {"svg"}，导出图可能是 svg。
_IMG_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
_DOC_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def _images_dir(doc_id: str) -> str:
    return os.path.join(_cache_root(), doc_id, "images")


def _extract_images(result) -> dict[str, str]:
    """从 MinerU 响应里收集 {图片名: data-url}，兼容顶层 / results dict / results list。"""
    images: dict[str, str] = {}

    def _merge(obj) -> None:
        if isinstance(obj, dict) and isinstance(obj.get("images"), dict):
            images.update(obj["images"])

    if isinstance(result, dict):
        _merge(result)
        results_val = result.get("results")
        if isinstance(results_val, dict):
            for v in results_val.values():
                _merge(v)
        elif isinstance(results_val, list):
            for item in results_val:
                _merge(item)
    return images


def _extract_content_list(result) -> list:
    """从 MinerU 响应里取 content_list（可能是 JSON 字符串），用于给图片起语义名。"""
    raw = None

    def _pick(obj):
        if isinstance(obj, dict):
            return obj.get("content_list")
        return None

    if isinstance(result, dict):
        raw = _pick(result)
        if raw is None:
            rv = result.get("results")
            if isinstance(rv, dict):
                for v in rv.values():
                    raw = _pick(v)
                    if raw is not None:
                        break
            elif isinstance(rv, list):
                for it in rv:
                    raw = _pick(it)
                    if raw is not None:
                        break
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def _build_image_rename_map(content_list: list) -> dict[str, str]:
    """学 mkp-api：用 content_list 的 page_idx + id 把哈希图名映射成 p{page}_{id}.jpg。

    返回 {MinerU 原始 basename(<hash>.jpg): 语义名 p{page}_{id}.jpg}。id 在每页内唯一，
    故语义名不冲突；不在 content_list 里的图（未被正文引用）保留原名。
    """
    mapping: dict[str, str] = {}
    for item in content_list or []:
        if not isinstance(item, dict):
            continue
        img_path = item.get("img_path")
        cid = item.get("id")
        if not img_path or cid is None:
            continue
        base = os.path.basename(img_path)
        ext = os.path.splitext(base)[1].lower() or ".jpg"
        mapping[base] = f"p{item.get('page_idx', 0)}_{cid}{ext}"
    return mapping


def _rename_md_images(md_text: str, rename_map: dict[str, str]) -> str:
    """把 Markdown 里的 images/<hash>.jpg 替换成语义名。basename 为长哈希，直接替换安全。"""
    for old_base, new_base in rename_map.items():
        if old_base != new_base:
            md_text = md_text.replace(old_base, new_base)
    return md_text


def _decode_data_url(data_url: str) -> bytes | None:
    try:
        if data_url.startswith("data:"):
            comma = data_url.find(",")
            if comma == -1:
                return None
            return base64.b64decode(data_url[comma + 1 :])
        return base64.b64decode(data_url)
    except Exception:
        return None


def _write_images(
    doc_id: str, images: dict[str, str], rename_map: dict[str, str] | None = None
) -> int:
    """把 {图片名: data-url} 解码落盘到 {doc_id}/images/，返回成功写入的张数。

    rename_map 命中的图改用语义名 p{page}_{id}.jpg 落盘（与改写后的 Markdown 引用一致）。
    """
    if not images:
        return 0
    rename_map = rename_map or {}
    out_dir = _images_dir(doc_id)
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for name, data_url in images.items():
        src_base = os.path.basename(name or "")
        if not src_base or src_base in (".", ".."):
            continue
        out_base = rename_map.get(src_base, src_base)
        if os.path.splitext(out_base)[1].lower() not in _IMG_EXT_OK:
            continue
        raw = _decode_data_url(data_url) if isinstance(data_url, str) else None
        if not raw:
            continue
        try:
            with open(os.path.join(out_dir, out_base), "wb") as f:
                f.write(raw)
            written += 1
        except OSError as e:
            logger.warning("write image %s/%s failed: %s", doc_id, out_base, e)
    return written


def _count_cached_images(doc_id: str) -> int:
    d = _images_dir(doc_id)
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d) if os.path.splitext(f)[1].lower() in _IMG_EXT_OK)


def resolve_cached_image(doc_id: str, rel_path: str) -> str | None:
    """把 (doc_id, 相对路径) 解析为已缓存图片的绝对路径；非法或不存在返回 None。

    防路径穿越：realpath 必须落在该 doc 的目录内；限定图片后缀；必须是已存在文件。
    """
    if not _DOC_ID_RE.match(doc_id or ""):
        return None
    doc_root = os.path.realpath(os.path.join(_cache_root(), doc_id))
    target = os.path.realpath(os.path.join(doc_root, rel_path or ""))
    if target != doc_root and not target.startswith(doc_root + os.sep):
        return None
    if os.path.splitext(target)[1].lower() not in _IMG_EXT_OK:
        return None
    if not os.path.isfile(target):
        return None
    return target


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_MD_IMAGE_REF = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _extract_outline(md_text: str, max_items: int = 40) -> list[str]:
    """提取 Markdown 章节目录（#/##/### ...），用于让模型选择性精读。"""
    items: list[str] = []
    for m in _HEADING_RE.finditer(md_text):
        level = len(m.group(1))
        title = m.group(2).strip()
        indent = "  " * (level - 1)
        items.append(f"{indent}- {title}")
        if len(items) >= max_items:
            items.append("  ...(目录已截断)")
            break
    return items


async def _download_pdf(url: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        trust_env=False,
        headers=_FETCH_HEADERS,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    lang: str = "ch",
    start_page: int = 0,
    end_page: int = 99999,
) -> tuple[str, dict[str, str], list]:
    """Send PDF bytes to MinerU, return (Markdown text, {图片名: data-url}, content_list)。"""
    files = [("files", (filename, io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "return_md": "true",
        "return_images": "true",
        "return_content_list": "true",
        "backend": settings.pdf_parse_backend,
        "parse_method": settings.pdf_parse_method,
        "formula_enable": str(settings.pdf_parse_formula_enable).lower(),
        "table_enable": str(settings.pdf_parse_table_enable).lower(),
        "start_page_id": str(start_page),
        "end_page_id": str(end_page),
    }
    if settings.pdf_parse_server_url:
        data["server_url"] = settings.pdf_parse_server_url
    if lang:
        data["lang_list"] = lang

    async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
        resp = await client.post(
            settings.pdf_parse_url,
            files=files,
            data=data,
        )
        resp.raise_for_status()
        result = resp.json()

    if isinstance(result, dict):
        md_text = result.get("markdown", "") or result.get("md", "") or result.get("md_content", "")
        if not md_text and "results" in result:
            results_val = result["results"]
            parts: list[str] = []
            if isinstance(results_val, dict):
                for v in results_val.values():
                    if isinstance(v, dict):
                        parts.append(v.get("md_content", "") or v.get("markdown", "") or v.get("md", ""))
                    elif isinstance(v, str):
                        parts.append(v)
            elif isinstance(results_val, list):
                for item in results_val:
                    if isinstance(item, dict):
                        parts.append(item.get("md_content", "") or item.get("markdown", "") or item.get("md", ""))
                    elif isinstance(item, str):
                        parts.append(item)
            md_text = "\n\n".join(p for p in parts if p)
        if not md_text:
            md_text = str(result)[:8000]
        return md_text, _extract_images(result), _extract_content_list(result)
    return str(result)[:8000], {}, []


def _build_persisted_block(
    doc_id: str,
    source_url: str,
    filename: str,
    size_mb: float,
    md_text: str,
) -> str:
    total_chars = len(md_text)
    preview_n = settings.pdf_preview_chars
    preview = md_text[:preview_n]
    outline = _extract_outline(md_text)
    outline_block = "\n".join(outline) if outline else "（未检测到 Markdown 标题）"
    fetch_time = datetime.now(_CST).strftime("%Y-%m-%d %H:%M UTC+8")

    img_count = _count_cached_images(doc_id)
    figure_line = (
        f"  • 本文档已缓存 {img_count} 张论文原图。讲解时可用 "
        f"`[figure:{doc_id}:images/<文件名>|图注]` 把图嵌进正文——"
        f"**仅限 pdf_read 原文里真实出现过的 `![](images/...)` 路径**。\n"
        if img_count
        else ""
    )

    return (
        f"<persisted-pdf>\n"
        f"**来源**: {source_url}\n"
        f"**文件**: {filename} ({size_mb:.1f} MB)\n"
        f"**解析时间**: {fetch_time}\n"
        f"**doc_id**: {doc_id}\n"
        f"**总字符数**: {total_chars}\n\n"
        f"**章节目录**:\n{outline_block}\n\n"
        f"**原文预览**（前 {min(preview_n, total_chars)} 字，未经任何 LLM 改写）:\n"
        f"---\n{preview}\n---\n\n"
        f"全文已完整缓存。要精读或核实数值，请调用：\n"
        f"  • `pdf_read(doc_id=\"{doc_id}\", offset=<char>, limit=<chars>)` —— 按字符分页读取\n"
        f"  • `pdf_grep(doc_id=\"{doc_id}\", pattern=<regex>, context=3)` —— 定位精确字符串/数字\n"
        f"  • `pdf_vision(doc_id=\"{doc_id}\", question=\"...\")` —— 图表/截图在 Markdown 中以图片形式存在时，用多模态阅读（仅同源的 MinerU 图片 URL 或 data:image）\n"
        f"{figure_line}"
        f"**引用论文数值前，必须先 grep 命中原文行；命中不到则必须标注「未在原文核实」。**\n"
        f"</persisted-pdf>"
    )


@tool(
    "pdf_parse",
    "下载 PDF（论文、报告），通过 MinerU 提取为 Markdown 并完整落盘缓存；返回 doc_id + 章节目录 + 原文预览。**不做 LLM 摘要**，保留所有数值/表格原文。要精读请配合 pdf_read / pdf_grep。",
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "PDF 文件的 URL 地址",
            },
            "lang": {
                "type": "string",
                "description": "PDF 语言：ch（中英文，默认）、en（英文）、japan（日文）等",
                "default": "ch",
            },
            "start_page": {
                "type": "integer",
                "description": "起始页码（从0开始），默认0",
                "default": 0,
            },
            "end_page": {
                "type": "integer",
                "description": "结束页码（从0开始），默认99999（全部）",
                "default": 99999,
            },
            "force_refresh": {
                "type": "boolean",
                "description": "是否忽略缓存重新解析，默认 false",
                "default": False,
            },
        },
        "required": ["url"],
    },
)
async def pdf_parse(args: dict) -> dict:
    url = args["url"]
    lang = args.get("lang", "ch")
    start_page = int(args.get("start_page", 0))
    end_page = int(args.get("end_page", 99999))
    force_refresh = bool(args.get("force_refresh", False))

    if not settings.pdf_parse_url:
        return {"content": [{"type": "text", "text": "PDF_PARSE_URL 未配置，无法解析 PDF。"}]}

    doc_id = _doc_id_for_url(url)
    filename = url.rsplit("/", 1)[-1] or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    if not force_refresh:
        cached = _load_cached_md(doc_id)
        if cached is not None:
            block = _build_persisted_block(
                doc_id=doc_id,
                source_url=url,
                filename=filename,
                size_mb=0.0,
                md_text=cached,
            )
            return {"content": [{"type": "text", "text": f"（命中缓存）\n{block}"}]}

    try:
        pdf_bytes = await _download_pdf(url)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"下载 PDF 失败：{e}\nURL: {url}"}]}

    size_mb = len(pdf_bytes) / (1024 * 1024)
    logger.info("PDF downloaded: %s (%.1f MB), sending to parser...", filename, size_mb)

    try:
        md_text, images, content_list = await _parse_pdf_bytes(
            pdf_bytes,
            filename=filename,
            lang=lang,
            start_page=start_page,
            end_page=end_page,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": f"PDF 解析服务调用失败：{e}"}]}

    if not md_text or len(md_text.strip()) < 20:
        return {"content": [{"type": "text", "text": f"PDF 解析结果为空，可能是扫描件或加密文件。\nURL: {url}"}]}

    # 学 mkp-api：用 content_list 把哈希图名映射成 p{page}_{id}.jpg，正文引用与落盘同步改名。
    rename_map = _build_image_rename_map(content_list)
    md_text = _rename_md_images(md_text, rename_map)

    try:
        _write_cache(doc_id, md_text, url, filename)
    except Exception as e:
        logger.warning("Failed to write PDF cache for %s: %s", doc_id, e)

    try:
        n_img = _write_images(doc_id, images, rename_map)
        if n_img:
            logger.info("PDF images cached: %s (%d imgs)", doc_id, n_img)
    except Exception as e:
        logger.warning("Failed to write PDF images for %s: %s", doc_id, e)

    block = _build_persisted_block(
        doc_id=doc_id,
        source_url=url,
        filename=filename,
        size_mb=size_mb,
        md_text=md_text,
    )
    return {"content": [{"type": "text", "text": block}]}


@tool(
    "pdf_read",
    "按字符范围读取已缓存 PDF 的原始 Markdown（由 pdf_parse 预先落盘）。用于精读某一章节——**返回的是未改写的原文**。超过安全限制会直接报错而非摘要。",
    {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "pdf_parse 返回的 doc_id",
            },
            "offset": {
                "type": "integer",
                "description": "起始字符位置（从0开始），默认0",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "读取字符数，默认 6000，最大受 PDF_READ_MAX_CHARS 限制",
                "default": 6000,
            },
        },
        "required": ["doc_id"],
    },
)
async def pdf_read(args: dict) -> dict:
    doc_id = args["doc_id"]
    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", 6000))

    md_text = _load_cached_md(doc_id)
    if md_text is None:
        return {"content": [{"type": "text", "text": f"未找到 doc_id={doc_id} 的缓存。请先调用 pdf_parse。"}]}

    total = len(md_text)
    if offset < 0 or offset >= total:
        return {"content": [{"type": "text", "text": f"offset={offset} 越界，全文共 {total} 字符。"}]}

    max_chars = settings.pdf_read_max_chars
    if limit > max_chars:
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"请求 limit={limit} 超过安全上限 {max_chars}。"
                    f"请缩小 limit 或多次分页读取（全文共 {total} 字符）。"
                ),
            }]
        }

    chunk = md_text[offset : offset + limit]
    end = offset + len(chunk)
    has_more = end < total
    footer = (
        f"\n\n---\n（doc_id={doc_id} · 已读 [{offset}:{end}] / {total}"
        + (f" · 继续读取：pdf_read(offset={end}, limit={limit})" if has_more else " · 已到末尾")
        + "）"
    )
    return {"content": [{"type": "text", "text": chunk + footer}]}


@tool(
    "pdf_grep",
    "在已缓存 PDF 的原始 Markdown 里做正则匹配，返回命中行 + 上下文（默认 3 行）。**这是引用论文数值/指标前的必经核实步骤**——grep 不到就说明该数字不在原文。",
    {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "pdf_parse 返回的 doc_id",
            },
            "pattern": {
                "type": "string",
                "description": "Python 正则（默认大小写不敏感）。例：`F1.{0,5}9[0-9]\\.[0-9]` 或 `BLEU`",
            },
            "context": {
                "type": "integer",
                "description": "每个命中上下文行数（前后各 N 行），默认 3",
                "default": 3,
            },
            "max_hits": {
                "type": "integer",
                "description": "最多返回命中数，默认 20",
                "default": 20,
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "是否大小写敏感，默认 false",
                "default": False,
            },
        },
        "required": ["doc_id", "pattern"],
    },
)
async def pdf_grep(args: dict) -> dict:
    doc_id = args["doc_id"]
    pattern = args["pattern"]
    context_n = int(args.get("context", 3))
    max_hits = int(args.get("max_hits", 20))
    case_sensitive = bool(args.get("case_sensitive", False))

    md_text = _load_cached_md(doc_id)
    if md_text is None:
        return {"content": [{"type": "text", "text": f"未找到 doc_id={doc_id} 的缓存。请先调用 pdf_parse。"}]}

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {"content": [{"type": "text", "text": f"正则编译失败：{e}"}]}

    lines = md_text.splitlines()
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if regex.search(line):
            hits.append((i, line))
            if len(hits) >= max_hits:
                break

    if not hits:
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"doc_id={doc_id} · pattern=`{pattern}` · **0 命中**。\n"
                    f"该模式不在原文中出现——若你准备引用相关数值，请标注「未在原文核实」。"
                ),
            }]
        }

    blocks: list[str] = []
    for idx, line in hits:
        start = max(0, idx - context_n)
        end = min(len(lines), idx + context_n + 1)
        snippet_lines = []
        for j in range(start, end):
            marker = ">>" if j == idx else "  "
            snippet_lines.append(f"{marker} L{j+1}: {lines[j]}")
        blocks.append("\n".join(snippet_lines))

    header = f"doc_id={doc_id} · pattern=`{pattern}` · 命中 {len(hits)} 处（共 {len(lines)} 行）：\n"
    body = "\n\n---\n\n".join(blocks)
    return {"content": [{"type": "text", "text": header + body}]}


_VISION_SYSTEM = """你是学术文献辅助助手。用户会附上从 PDF 解析得到的 Markdown 片段（可能含图表截图）。
请根据可见的图片与文字作答：明确区分「图中可见」「文中文字」「无法从当前材料判断」。
若看不清或图中无相关数字，如实说明。用户用中文提问则用中文回答。"""


@tool(
    "pdf_vision",
    "对已 pdf_parse 缓存的 Markdown 中嵌入的图片（![](...) 或 data:image）调用 Kimi Vision 多模态理解。"
    "用于图表、曲线、截图中的信息；**不会**自动抓取外链图片，仅同源 MinerU 或内联 base64。",
    {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "pdf_parse 返回的 doc_id"},
            "question": {
                "type": "string",
                "description": "要问视觉模型的问题，例如：Figure 4 中各曲线趋势与图例含义",
            },
            "max_images": {
                "type": "integer",
                "description": "最多送入几张图（按 Markdown 中出现顺序），默认取环境配置",
                "default": 0,
            },
        },
        "required": ["doc_id", "question"],
    },
)
async def pdf_vision(args: dict) -> dict:
    doc_id = args["doc_id"]
    question = (args.get("question") or "").strip()
    max_i = int(args.get("max_images") or 0) or settings.pdf_vision_max_images

    if not settings.anthropic_auth_token:
        return {"content": [{"type": "text", "text": "未配置 ANTHROPIC_AUTH_TOKEN，无法调用 Vision。"}]}
    if not settings.pdf_parse_url:
        return {"content": [{"type": "text", "text": "未配置 PDF_PARSE_URL。"}]}

    md_text = _load_cached_md(doc_id)
    if md_text is None:
        return {"content": [{"type": "text", "text": f"未找到 doc_id={doc_id} 的缓存。请先调用 pdf_parse。"}]}

    if not _MD_IMAGE_REF.search(md_text):
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"doc_id={doc_id} 的 Markdown 中未发现 `![](...)` 或 `data:image` 图片引用。\n"
                    "若图表仅在 PDF 内而未导出为图片，请改用 pdf_read / pdf_grep 阅读文字部分。"
                ),
            }]
        }

    excerpt = md_text[:6000]
    preamble = (
        "以下为该 PDF 对应 Markdown 的前 6000 字符（供定位上下文；图片另附为独立多模态块）：\n\n"
        f"```markdown\n{excerpt}\n```\n\n"
    )

    try:
        parts, warnings = await build_pdf_markdown_vision_parts(
            md_text,
            settings.pdf_parse_url,
            preamble=preamble,
            question=question,
            max_images=max_i,
            max_bytes_per_image=settings.pdf_vision_max_image_bytes,
            max_edge=settings.pdf_vision_max_edge,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": f"构建多模态内容失败：{e}"}]}

    image_count = sum(1 for p in parts if p.get("type") == "image_url")
    if image_count == 0:
        warn_txt = "\n".join(warnings) if warnings else "（无详细原因）"
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"未能加载任何图片（共尝试 Markdown 中的引用）。\n{warn_txt}\n\n"
                    "请确认 MinerU 导出的图片 URL 与 PDF_PARSE_URL 同源，或使用内联 data:image。"
                ),
            }]
        }

    if warnings:
        preamble_note = "\n\n[图片加载警告]\n" + "\n".join(warnings[:20])
        parts[0] = {
            "type": "text",
            "text": parts[0].get("text", "") + preamble_note,
        }

    model = settings.pdf_vision_model or settings.web_fetch_summary_model
    try:
        answer = await run_kimi_vision_chat(
            system_prompt=_VISION_SYSTEM,
            user_content_parts=parts,
            anthropic_base_url=settings.anthropic_base_url,
            auth_token=settings.anthropic_auth_token,
            model=model,
            timeout=120.0,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Kimi Vision 调用失败：{e}"}]}

    header = f"doc_id={doc_id} · 已送 {image_count} 张图 · model=`{model}`\n\n"
    return {"content": [{"type": "text", "text": header + answer}]}

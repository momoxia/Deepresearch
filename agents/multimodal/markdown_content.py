"""
Build OpenAI-style multimodal user `content` from MinerU PDF Markdown for Kimi Vision.

Kimi: remote image URLs are not supported; use data URLs or file upload + ms://.
Resolution: align with official guidance (max edge 4096).
"""
from __future__ import annotations

import base64
import io
import ipaddress
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DeepResearch/1.0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _chat_api_base(anthropic_base_url: str) -> str:
    base = anthropic_base_url.rstrip("/")
    if base.endswith("/anthropic"):
        base = base[: -len("/anthropic")]
    return base


def _mineru_origin(pdf_parse_url: str) -> str:
    p = urlparse(pdf_parse_url)
    if not p.scheme or not p.netloc:
        raise ValueError("PDF_PARSE_URL must include scheme and host")
    return f"{p.scheme}://{p.netloc}/"


def _origin_key(url: str) -> tuple[str, str, int] | None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    port = p.port or (443 if p.scheme == "https" else 80)
    return (p.scheme.lower(), p.hostname.lower(), port)


def _same_origin(abs_url: str, pdf_parse_url: str) -> bool:
    a = _origin_key(abs_url)
    b = _origin_key(pdf_parse_url)
    return a is not None and b is not None and a == b


def _blocked_hostname(hostname: str) -> bool:
    h = hostname.lower().rstrip(".")
    if h == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    except ValueError:
        pass
    return False


def _resolve_image_ref(ref: str, mineru_origin: str) -> str:
    ref = ref.strip()
    if ref.startswith("data:image"):
        return ref
    return urljoin(mineru_origin, ref)


def _guess_mime_from_bytes(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _maybe_downscale(data: bytes, max_edge: int) -> tuple[bytes, str]:
    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        return data, _guess_mime_from_bytes(data)

    try:
        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        w, h = im.size
        if w <= max_edge and h <= max_edge:
            mime = _guess_mime_from_bytes(data)
            return data, mime
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        if im.mode == "RGBA":
            im.save(buf, format="PNG")
            return buf.getvalue(), "image/png"
        im.convert("RGB").save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        logger.debug("Pillow resize skipped", exc_info=True)
        return data, _guess_mime_from_bytes(data)


async def _fetch_one_image(
    client: httpx.AsyncClient,
    abs_url: str,
    *,
    max_bytes: int,
    max_edge: int,
) -> tuple[str | None, str | None]:
    try:
        r = await client.get(abs_url, follow_redirects=True)
        r.raise_for_status()
        data = r.content
        if len(data) > max_bytes:
            return None, f"skip (>{max_bytes}b): {abs_url[:80]}"
        ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct and not ct.startswith("image/"):
            return None, f"skip (non-image {ct}): {abs_url[:80]}"
        data2, mime = _maybe_downscale(data, max_edge)
        b64 = base64.standard_b64encode(data2).decode("ascii")
        return f"data:{mime};base64,{b64}", None
    except Exception as e:
        return None, f"fetch failed {abs_url[:80]}: {e}"


async def build_pdf_markdown_vision_parts(
    md_text: str,
    pdf_parse_url: str,
    *,
    preamble: str,
    question: str,
    max_images: int,
    max_bytes_per_image: int,
    max_edge: int,
) -> tuple[list[dict], list[str]]:
    mineru_origin = _mineru_origin(pdf_parse_url)
    seen: set[str] = set()
    warnings: list[str] = []
    data_urls: list[str] = []

    for m in _MD_IMAGE.finditer(md_text):
        if len(data_urls) >= max_images:
            break
        raw = m.group(1).strip().strip('"').strip("'")
        if not raw:
            continue
        abs_url = _resolve_image_ref(raw, mineru_origin)
        if abs_url in seen:
            continue
        seen.add(abs_url)

        if abs_url.startswith("data:image"):
            if len(abs_url) > max_bytes_per_image * 2:
                warnings.append("skip (inline data:image too large)")
                continue
            data_urls.append(abs_url)
            continue

        if _origin_key(abs_url) is None or not _same_origin(abs_url, pdf_parse_url):
            warnings.append(f"skip (cross-origin): {abs_url[:120]}")
            continue
        host = urlparse(abs_url).hostname or ""
        if _blocked_hostname(host):
            warnings.append(f"skip (blocked host): {host}")
            continue

        async with httpx.AsyncClient(timeout=60.0, trust_env=False, headers=_FETCH_HEADERS) as client:
            data_url, warn = await _fetch_one_image(
                client,
                abs_url,
                max_bytes=max_bytes_per_image,
                max_edge=max_edge,
            )
        if warn:
            warnings.append(warn)
        if data_url:
            data_urls.append(data_url)

    parts: list[dict] = [{"type": "text", "text": preamble}]
    for u in data_urls:
        parts.append({"type": "image_url", "image_url": {"url": u}})
    parts.append({"type": "text", "text": question})
    return parts, warnings


async def run_kimi_vision_chat(
    *,
    system_prompt: str,
    user_content_parts: list[dict],
    anthropic_base_url: str,
    auth_token: str,
    model: str,
    timeout: float = 120.0,
    temperature: float = 1.0,
    max_tokens: int = 4096,
) -> str:
    # temperature defaults to 1.0: native-multimodal kimi-k2.x reject any other value
    # ("only 1 is allowed for this model") and moonshot-v1-*-vision-preview accept it too.
    # max_tokens is generous because k2.x are thinking models — reasoning_content is
    # billed against the budget before the visible answer, so a tight cap truncates it.
    if not auth_token:
        raise ValueError("ANTHROPIC_AUTH_TOKEN is empty")

    api_url = f"{_chat_api_base(anthropic_base_url)}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content_parts},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.post(api_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    # thinking models put the answer in `content` and the chain-of-thought in
    # `reasoning_content`; content may be None if the budget was exhausted.
    return (data["choices"][0]["message"].get("content") or "").strip()

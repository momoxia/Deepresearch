"""图文混排：把 pdf_parse 落盘的论文原图按 doc_id + 相对路径回传给前端。

前端在正文里遇到 [figure:<doc_id>:images/<file>] 标记时，会向
`/api/pdf-image/<doc_id>/images/<file>` 请求图片。路径合法性与防穿越由
agents.tools.pdf_tools.resolve_cached_image 统一把关。
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from agents.tools.pdf_tools import resolve_cached_image

router = APIRouter(prefix="/pdf-image", tags=["pdf-image"])

_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


@router.get("/{doc_id}/{path:path}")
async def get_pdf_image(doc_id: str, path: str):
    target = resolve_cached_image(doc_id, path)
    if not target:
        raise HTTPException(
            status_code=404,
            detail="图片不存在或路径非法（旧文档需 pdf_parse(force_refresh=true) 重解析）",
        )
    media = _MEDIA.get(os.path.splitext(target)[1].lower(), "application/octet-stream")
    # 文件名是内容哈希，内容不可变 → 长缓存。
    return FileResponse(
        target,
        media_type=media,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )

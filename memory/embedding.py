"""
Embedding utilities for semantic memory retrieval (DashScope OpenAI-compatible).
"""
import json
import logging
from typing import Optional

import httpx
import numpy as np

from config import settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str) -> Optional[list[float]]:
    if not settings.embedding_model_api_key:
        return None

    url = f"{settings.embedding_model_url.rstrip('/')}/embeddings"

    payload = {
        "model": settings.embedding_model_name,
        "input": text[:8000],
    }
    headers = {
        "Authorization": f"Bearer {settings.embedding_model_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        logger.warning("Embedding API failed (will skip vector search): %s", e)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def parse_embedding(embedding_json: Optional[str]) -> Optional[list[float]]:
    if not embedding_json:
        return None
    try:
        return json.loads(embedding_json)
    except (json.JSONDecodeError, TypeError):
        return None

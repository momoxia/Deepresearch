"""
Small Kimi Anthropic-compatible text client.

Use this for plain text helper calls (summaries, memory extraction, titles).
The main Agent SDK already talks to the same `/anthropic/v1/messages` endpoint.
"""
from __future__ import annotations

import httpx

from config import settings


def _messages_url() -> str:
    base_url = settings.anthropic_base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return f"{base_url}/messages"
    return f"{base_url}/v1/messages"


def _normalize_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        if role in {"user", "assistant"}:
            anthropic_messages.append({"role": role, "content": str(content)})
    return "\n\n".join(system_parts), anthropic_messages


async def chat_text(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: float = 60,
) -> str:
    if not settings.anthropic_auth_token:
        raise ValueError("ANTHROPIC_AUTH_TOKEN is empty")

    system_text, anthropic_messages = _normalize_messages(messages)
    payload: dict = {
        "model": model or settings.anthropic_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": anthropic_messages,
    }
    if system_text:
        payload["system"] = system_text

    headers = {
        "x-api-key": settings.anthropic_auth_token,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.post(_messages_url(), json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    blocks = data.get("content") or []
    texts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(texts).strip()

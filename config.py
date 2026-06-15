import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_base_url: str = Field(
        default="https://api.moonshot.ai/anthropic",
        alias="ANTHROPIC_BASE_URL",
    )
    anthropic_auth_token: str = Field(default="", alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_model: str = Field(default="kimi-k2.5", alias="ANTHROPIC_MODEL")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./deepresearch.db",
        alias="DATABASE_URL",
    )

    app_title: str = Field(default="Deep Research Agent", alias="APP_TITLE")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    # APP_DEBUG avoids clash with shell/build `DEBUG=release` (non-boolean).
    debug: bool = Field(default=True, alias="APP_DEBUG")

    serper_api_key: str = Field(default="", alias="SERPER_API_KEY")

    web_fetch_timeout: int = Field(default=30, alias="WEB_FETCH_TIMEOUT")
    web_fetch_max_chars: int = Field(default=4000, alias="WEB_FETCH_MAX_CHARS")
    web_fetch_summary_model: str = Field(
        default="kimi-k2-turbo-preview", alias="WEB_FETCH_SUMMARY_MODEL"
    )

    firecrawl_api_key: str = Field(default="", alias="FIRECRAWL_API_KEY")

    pdf_parse_url: str = Field(
        default="http://127.0.0.1:8000/file_parse",
        alias="PDF_PARSE_URL",
    )
    pdf_cache_dir: str = Field(
        default="./data/pdf_cache",
        alias="PDF_CACHE_DIR",
    )
    pdf_preview_chars: int = Field(default=2500, alias="PDF_PREVIEW_CHARS")
    pdf_read_max_chars: int = Field(default=12000, alias="PDF_READ_MAX_CHARS")

    pdf_vision_max_images: int = Field(default=6, alias="PDF_VISION_MAX_IMAGES")
    pdf_vision_max_image_bytes: int = Field(default=8_388_608, alias="PDF_VISION_MAX_IMAGE_BYTES")
    pdf_vision_max_edge: int = Field(default=4096, alias="PDF_VISION_MAX_EDGE")
    pdf_vision_model: str = Field(default="", alias="PDF_VISION_MODEL")

    embedding_model_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="EMBEDDING_MODEL_URL",
    )
    embedding_model_api_key: str = Field(default="", alias="EMBEDDING_MODEL_API_KEY")
    embedding_model_name: str = Field(default="text-embedding-v4", alias="EMBEDDING_MODEL_NAME")

    memory_summary_threshold: int = Field(default=10, alias="MEMORY_SUMMARY_THRESHOLD")

    # 隔离 SDK 子进程的 claude-cli 配置目录（含 transcripts），避免污染用户 ~/.claude
    claude_config_dir: str = Field(default="./.claude-runtime", alias="CLAUDE_CONFIG_DIR")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8808, alias="API_PORT")
    # uvicorn 多进程；>1 时与 reload 互斥。SQLite 并发写能力有限，多 worker 更适 PostgreSQL 等。
    uvicorn_workers: int = Field(default=1, ge=1, alias="UVICORN_WORKERS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def configure_kimi_env() -> None:
    os.environ.setdefault("ANTHROPIC_BASE_URL", settings.anthropic_base_url)
    os.environ.setdefault("ANTHROPIC_AUTH_TOKEN", settings.anthropic_auth_token)
    os.environ.setdefault("ANTHROPIC_MODEL", settings.anthropic_model)
    if settings.anthropic_auth_token:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_auth_token)

    # claude-agent-sdk 会启动 `claude` CLI 子进程，默认把每次会话的 transcript
    # 写到 ~/.claude/projects/<cwd-encoded>/*.jsonl —— 与用户本机 Claude Code
    # 的会话目录同名，导致后端用户会话污染 CC 的 /resume 列表。
    # 通过 CLAUDE_CONFIG_DIR 把 SDK 子进程的配置根切到仓库内独立目录。
    config_dir = Path(settings.claude_config_dir).expanduser().resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CLAUDE_CONFIG_DIR"] = str(config_dir)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    from db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _migrate_memory_columns()


async def _migrate_memory_columns() -> None:
    import sqlalchemy as sa

    migrations = [
        ("memories", "source", "VARCHAR(30) DEFAULT 'conversation'"),
        ("memories", "access_count", "INTEGER DEFAULT 0"),
        ("memories", "last_accessed_at", "DATETIME"),
        ("memories", "embedding_json", "TEXT"),
        ("memories", "archived", "INTEGER DEFAULT 0"),
        ("memories", "episode", "TEXT"),
        ("memories", "foresight_json", "TEXT"),
        ("memories", "related_keys", "TEXT"),
        ("conversations", "title", "VARCHAR(200)"),
        ("projects", "folder_id", "INTEGER"),
    ]
    async with engine.begin() as conn:
        for table, col_name, col_def in migrations:
            try:
                await conn.execute(
                    sa.text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                )
            except Exception:
                pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

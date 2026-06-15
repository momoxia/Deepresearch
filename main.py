import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import configure_kimi_env, settings
from db.database import init_db

configure_kimi_env()

from api.routes import artifacts, chat, folders, projects  # noqa: E402

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Deep research assistant: web tools + full memory stack (Kimi + Agent SDK)",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(folders.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    await init_db()


@app.get("/", tags=["health"])
async def root():
    return {
        "service": settings.app_title,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    _kw = dict(
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    if settings.uvicorn_workers > 1:
        uvicorn.run("main:app", workers=settings.uvicorn_workers, **_kw)
    else:
        uvicorn.run(
            "main:app",
            reload=settings.debug,
            reload_excludes=[
                "data/*",
                "data/**/*",
                "node_modules/*",
                "node_modules/**/*",
                "frontend/*",
                "frontend/**/*",
                "memory/*",
                "deepresearch.db*",
            ],
            **_kw,
        )

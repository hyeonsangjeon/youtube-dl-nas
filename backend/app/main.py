"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.models.download import Download  # noqa: F401 — Base.metadata 등록용
from app.routers import auth, download, health, legacy
from app.services.download_manager import download_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup, manage download worker."""
    await init_db()
    await download_manager.start()
    yield
    await download_manager.stop()


app = FastAPI(
    title="youtube-dl-nas v2",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(download.router)
app.include_router(legacy.router)

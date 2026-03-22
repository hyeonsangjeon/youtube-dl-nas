"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.models.download import Download  # noqa: F401 — Base.metadata 등록용
from app.routers import auth, download, files, health, legacy
from app.services.download_manager import download_manager
from app.services.scheduler import scheduler
from app.ws.handler import router as ws_router
from app.ws.manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup, manage download worker."""
    await init_db()
    download_manager.set_broadcast(ws_manager.broadcast)
    await download_manager.start()
    await scheduler.start()
    yield
    await scheduler.stop()
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
app.include_router(files.router)
app.include_router(legacy.router)
app.include_router(ws_router)

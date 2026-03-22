"""Async download queue manager with a single background worker."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.download import Download
from app.services.ytdlp_service import extract_metadata, run_download

logger = logging.getLogger(__name__)


class DownloadManager:
    """Manages a FIFO download queue with a single async worker."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._current_download_id: str | None = None
        self._broadcast_fn: Callable[..., Awaitable[None]] | None = None

    def set_broadcast(self, fn: Callable[..., Awaitable[None]]) -> None:
        """Set broadcast callback. Called from main.py lifespan."""
        self._broadcast_fn = fn

    @property
    def current_download_id(self) -> str | None:
        """Return the ID of the currently processing download."""
        return self._current_download_id

    @property
    def queue_size(self) -> int:
        """Return the number of items waiting in the queue."""
        return self._queue.qsize()

    async def _broadcast(self, message: dict) -> None:
        """Send a message via the broadcast callback if set."""
        if self._broadcast_fn:
            await self._broadcast_fn(message)

    async def start(self) -> None:
        """Start the background worker."""
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("DownloadManager worker started")

    async def stop(self) -> None:
        """Stop the background worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("DownloadManager worker stopped")

    async def enqueue(self, url: str, resolution: str = "best") -> str:
        """Create a download record and add it to the queue."""
        download_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            download = Download(
                id=download_id,
                url=url,
                resolution=resolution,
                status="queued",
                progress=0.0,
            )
            session.add(download)
            await session.commit()

        await self._queue.put(download_id)
        logger.info("Enqueued download %s for %s", download_id, url)
        return download_id

    async def get_queue_size(self) -> int:
        """Return the number of items waiting in the queue."""
        return self._queue.qsize()

    async def _worker(self) -> None:
        """Continuously process downloads from the queue."""
        while True:
            download_id = await self._queue.get()
            self._current_download_id = download_id
            try:
                await self._process_download(download_id)
            except Exception as exc:
                logger.exception("Error processing download %s", download_id)
                await self._update_status(download_id, "failed")
                await self._broadcast({
                    "type": "failed",
                    "data": {"download_id": download_id, "error": str(exc)},
                })
            finally:
                self._current_download_id = None
                self._queue.task_done()

    async def _process_download(self, download_id: str) -> None:
        """Execute a single download: metadata → download → DB update."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Download).where(Download.id == download_id)
            )
            download = result.scalar_one_or_none()
            if not download:
                logger.error("Download %s not found in DB", download_id)
                return

            url = download.url
            resolution = download.resolution or "best"

        # Extract metadata
        meta = await extract_metadata(url)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Download).where(Download.id == download_id)
            )
            download = result.scalar_one_or_none()
            if download:
                download.title = meta.title
                download.channel = meta.channel
                download.thumbnail_url = meta.thumbnail_url
                download.status = "downloading"
                download.progress = 5.0
                await session.commit()

        await self._broadcast({
            "type": "metadata",
            "data": {
                "download_id": download_id,
                "title": meta.title,
                "channel": meta.channel,
                "thumbnail_url": meta.thumbnail_url,
            },
        })

        # Run download and track progress
        async for progress in run_download(url, resolution):
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Download).where(Download.id == download_id)
                )
                download = result.scalar_one_or_none()
                if download:
                    download.progress = progress.percent
                    download.status = progress.status
                    if progress.filename:
                        download.filename = progress.filename
                        download.filepath = f"{settings.DOWNLOAD_DIR}/{progress.filename}"
                    if progress.status == "completed":
                        download.progress = 100.0
                        download.completed_at = datetime.now(timezone.utc)
                    await session.commit()

            await self._broadcast({
                "type": "progress",
                "data": {
                    "download_id": download_id,
                    "percent": progress.percent,
                    "status": progress.status,
                },
            })

            if progress.status == "completed":
                await self._broadcast({
                    "type": "complete",
                    "data": {
                        "download_id": download_id,
                        "filename": progress.filename,
                        "status": "completed",
                    },
                })

    async def _update_status(self, download_id: str, status: str) -> None:
        """Update the status of a download record."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Download).where(Download.id == download_id)
            )
            download = result.scalar_one_or_none()
            if download:
                download.status = status
                await session.commit()


download_manager = DownloadManager()

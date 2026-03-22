"""yt-dlp auto-update scheduler."""

import asyncio
import logging

logger = logging.getLogger(__name__)

UPDATE_INTERVAL_SECONDS = 3600  # 1 hour


async def _update_ytdlp() -> None:
    """Run yt-dlp -U to update to the latest version."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "-U",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("yt-dlp update timed out")
            return
        if proc.returncode == 0:
            logger.info("yt-dlp updated: %s", stdout.decode().strip())
        else:
            logger.warning("yt-dlp update failed: %s", stderr.decode().strip())
    except Exception:
        logger.exception("Failed to run yt-dlp update")


async def _scheduler_loop() -> None:
    """Periodically update yt-dlp."""
    while True:
        await _update_ytdlp()
        await asyncio.sleep(UPDATE_INTERVAL_SECONDS)


class Scheduler:
    """Manages the yt-dlp update background task."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the periodic update task."""
        self._task = asyncio.create_task(_scheduler_loop())
        logger.info("yt-dlp update scheduler started (interval: %ds)", UPDATE_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Cancel the periodic update task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("yt-dlp update scheduler stopped")


scheduler = Scheduler()

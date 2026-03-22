"""yt-dlp async wrapper for metadata extraction and downloads."""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import AsyncGenerator

from app.config import settings

UNSAFE_CHARS_PATTERN = "[\\\\/:*?\"'<>|&+\\$%@!~`=;,^#(){}\\[\\] ]"
SAFE_REPLACEMENT = "_"


@dataclass
class VideoMetadata:
    """Extracted video metadata."""

    title: str | None = None
    channel: str | None = None
    thumbnail_url: str | None = None


@dataclass
class DownloadProgress:
    """Progress update from a running download."""

    percent: float
    status: str  # "downloading", "merging", "completed", "failed"
    filename: str | None = None


async def extract_metadata(url: str) -> VideoMetadata:
    """Extract title, channel, and thumbnail from a URL using yt-dlp --dump-json."""
    cmd = ["yt-dlp", "--dump-json", "--no-download", "--no-warnings", url]
    if settings.PROXY:
        cmd.insert(1, "--proxy")
        cmd.insert(2, settings.PROXY)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode().strip().split("\n")[0])
            return VideoMetadata(
                title=data.get("title"),
                channel=data.get("uploader"),
                thumbnail_url=data.get("thumbnail"),
            )
    except Exception:
        pass
    return VideoMetadata()


def build_download_cmd(url: str, resolution: str) -> list[str]:
    """Build yt-dlp command arguments based on resolution. Mirrors v1 logic."""
    download_dir = settings.DOWNLOAD_DIR
    incomplete_dir = os.path.join(download_dir, ".incomplete")

    base = ["yt-dlp", "--retry-sleep", "1"]
    if settings.PROXY:
        base.extend(["--proxy", settings.PROXY])
    base.extend([
        "--replace-in-metadata", "title", UNSAFE_CHARS_PATTERN, SAFE_REPLACEMENT,
    ])

    if resolution == "best":
        return [
            *base,
            "-o", f"{incomplete_dir}/%(title)s.%(ext)s",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "--exec", f"touch {{}} && mv {{}} {download_dir}/",
            "--merge-output-format", "mp4",
            url,
        ]
    elif resolution in ("audio-m4a", "audio"):
        return [
            *base,
            "-o", f"{incomplete_dir}/%(title)s.%(ext)s",
            "-f", "bestaudio[ext=m4a]",
            "--exec", f"touch {{}} && mv {{}} {download_dir}/",
            url,
        ]
    elif resolution == "audio-mp3":
        return [
            *base,
            "-o", f"{incomplete_dir}/%(title)s.%(ext)s",
            "-f", "bestaudio[ext=m4a]",
            "-x", "--audio-format", "mp3",
            "--exec", f"touch {{}} && mv {{}} {download_dir}/",
            url,
        ]
    elif re.match(r"(vtt|srt)", resolution):
        parts = resolution.split("|")
        sub_format = parts[0]
        sub_lang = parts[1] if len(parts) > 1 else "en"
        return [
            *base,
            "-o", f"{download_dir}/%(title)s.%(ext)s",
            "--write-auto-subs", "--sub-langs", sub_lang,
            "--sub-format", sub_format, "--skip-download",
            url,
        ]
    else:
        # e.g. "1080p" → height<=1080
        height = resolution.rstrip("p")
        return [
            *base,
            "-o", f"{incomplete_dir}/%(title)s.%(ext)s",
            "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]",
            "--exec", f"touch {{}} && mv {{}} {download_dir}/",
            url,
        ]


async def run_download(url: str, resolution: str) -> AsyncGenerator[DownloadProgress, None]:
    """Run yt-dlp download and yield progress updates."""
    cmd = build_download_cmd(url, resolution)
    download_dir = settings.DOWNLOAD_DIR
    is_subtitle = bool(re.match(r"(vtt|srt)", resolution))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    filename: str | None = None
    filepath: str | None = None
    current_progress = 0.0

    while True:
        line_bytes = await proc.stdout.readline()
        if not line_bytes:
            break
        line = line_bytes.decode(errors="replace").strip()

        # Extract filename
        if is_subtitle and not filepath:
            m = re.search(
                r"\[(?:info|download)\] (?:Writing video subtitles to|Destination): (.+?\.(srt|vtt))",
                line,
            )
            if m:
                filepath = m.group(1)
                filename = os.path.basename(filepath)
        elif not filepath:
            m = re.search(
                r"touch\s+['\"]?(.+?)['\"]?\s+&&\s+mv\s+['\"]?(.+?)['\"]?\s+",
                line,
            )
            if m:
                source_path = m.group(2)
                filename = os.path.basename(source_path)
                filepath = os.path.join(download_dir, filename)

        # Progress extraction
        progress_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
        if progress_match:
            raw_progress = float(progress_match.group(1))
            adjusted = 5 + (raw_progress * 0.90)
            if abs(adjusted - current_progress) >= 1:
                current_progress = adjusted
                yield DownloadProgress(
                    percent=adjusted,
                    status="downloading",
                    filename=filename,
                )

        # Merge detection
        if "[Merger] Merging formats" in line:
            current_progress = 95.0
            yield DownloadProgress(
                percent=95.0,
                status="merging",
                filename=filename,
            )

    await proc.wait()

    if proc.returncode == 0:
        yield DownloadProgress(percent=100.0, status="completed", filename=filename)
    else:
        yield DownloadProgress(percent=current_progress, status="failed", filename=filename)

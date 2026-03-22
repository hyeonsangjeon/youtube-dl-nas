"""File serving endpoint for downloading completed files."""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.download import Download

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{download_id}")
async def serve_file(
    download_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> FileResponse:
    """Serve a downloaded file by its download ID (JWT required)."""
    result = await db.execute(select(Download).where(Download.id == download_id))
    download = result.scalar_one_or_none()

    if not download:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download not found")

    if not download.filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not available")

    file_path = os.path.join(settings.DOWNLOAD_DIR, download.filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    # Path traversal prevention
    real_file_path = os.path.realpath(file_path)
    real_download_dir = os.path.realpath(settings.DOWNLOAD_DIR)
    try:
        common = os.path.commonpath([real_file_path, real_download_dir])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if common != real_download_dir:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return FileResponse(
        path=file_path,
        filename=download.filename,
        media_type="application/octet-stream",
    )

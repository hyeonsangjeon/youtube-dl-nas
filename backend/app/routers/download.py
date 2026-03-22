"""v2 download API endpoints (JWT-protected)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.download import Download
from app.schemas.download import (
    DownloadCreate,
    DownloadHistoryResponse,
    DownloadResponse,
)
from app.services.download_manager import download_manager

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadResponse, status_code=status.HTTP_201_CREATED)
async def create_download(
    request: DownloadCreate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> DownloadResponse:
    """Enqueue a new download."""
    if not request.url or not request.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL: must start with http:// or https://",
        )
    download_id = await download_manager.enqueue(request.url, request.resolution)
    result = await db.execute(select(Download).where(Download.id == download_id))
    download = result.scalar_one_or_none()
    if not download:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create download record",
        )
    return DownloadResponse.model_validate(download)


@router.get("/history", response_model=DownloadHistoryResponse)
async def get_history(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> DownloadHistoryResponse:
    """Retrieve download history with pagination."""
    count_result = await db.execute(select(func.count(Download.id)))
    total = count_result.scalar()

    result = await db.execute(
        select(Download)
        .order_by(Download.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = [DownloadResponse.model_validate(row) for row in result.scalars().all()]
    return DownloadHistoryResponse(total=total, items=items)


@router.delete("/history/{download_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_item(
    download_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> None:
    """Delete a download history record (DB only, no file deletion)."""
    result = await db.execute(select(Download).where(Download.id == download_id))
    download = result.scalar_one_or_none()
    if not download:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Download record not found",
        )
    await db.delete(download)

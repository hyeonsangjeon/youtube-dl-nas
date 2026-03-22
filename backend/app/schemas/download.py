"""Download Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DownloadCreate(BaseModel):
    """Request schema for creating a new download."""

    url: str
    resolution: str = "best"


class DownloadResponse(BaseModel):
    """Response schema for a single download item."""

    id: str
    url: str
    title: Optional[str] = None
    channel: Optional[str] = None
    thumbnail_url: Optional[str] = None
    resolution: Optional[str] = None
    status: str
    progress: float
    filepath: Optional[str] = None
    filename: Optional[str] = None
    filesize: Optional[int] = None
    duration: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DownloadHistoryResponse(BaseModel):
    """Response schema for paginated download history."""

    total: int
    items: list[DownloadResponse]

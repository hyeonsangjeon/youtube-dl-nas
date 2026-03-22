"""Common Pydantic schemas shared across the application."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for the /health endpoint."""

    status: str
    version: str


class LegacyDownloadRequest(BaseModel):
    """Request schema matching the v1 /youtube-dl/rest API spec."""

    url: str
    resolution: str = "best"
    id: str = ""
    pw: str = ""


class LegacyDownloadResponse(BaseModel):
    """Response schema matching the v1 /youtube-dl/rest API spec."""

    success: bool
    msg: str
    remaining_downloading_count: str = "0"

    model_config = {"populate_by_name": True}

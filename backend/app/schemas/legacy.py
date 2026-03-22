"""Legacy v1 API request/response schemas."""

from pydantic import BaseModel


class LegacyDownloadRequest(BaseModel):
    """Request body for POST /youtube-dl/rest (v1 compatible)."""

    url: str
    resolution: str = "best"
    id: str = ""
    pw: str = ""

"""Legacy v1 API compatibility router.

Maintains backward compatibility with the original youtube-dl-nas REST API
so that existing external integrations continue to work without changes.
Wave 2 will replace this stub with real download logic and auth validation.
"""

from fastapi import APIRouter

from app.schemas.common import LegacyDownloadRequest, LegacyDownloadResponse

router = APIRouter(tags=["legacy"])


@router.post("/youtube-dl/rest", response_model=LegacyDownloadResponse)
async def legacy_download(request: LegacyDownloadRequest) -> LegacyDownloadResponse:
    """Handle legacy download requests with the original v1 response format.

    Wave 1 stub: returns a fixed success response without authentication or
    actual download processing. Full implementation deferred to Wave 2.
    """
    return LegacyDownloadResponse(
        success=True,
        msg="download has started",
        remaining_downloading_count="0",
    )

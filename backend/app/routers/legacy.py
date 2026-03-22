"""Legacy v1 API compatibility router (POST /youtube-dl/rest)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.legacy import LegacyDownloadRequest
from app.services.auth_service import verify_credentials
from app.services.download_manager import download_manager

router = APIRouter(tags=["legacy"])


@router.post("/youtube-dl/rest")
async def legacy_download(request: LegacyDownloadRequest) -> JSONResponse:
    """Handle legacy download requests with the original v1 response format.

    Always returns HTTP 200 for backward compatibility — errors are
    communicated via the JSON body.
    """
    if not verify_credentials(request.id, request.pw):
        return JSONResponse(
            content={"success": False, "msg": "Invalid password or account."}
        )

    remaining = str(await download_manager.get_queue_size())
    await download_manager.enqueue(request.url, request.resolution)

    return JSONResponse(
        content={
            "success": True,
            "msg": "download has started",
            "Remaining downloading count": remaining,
        }
    )

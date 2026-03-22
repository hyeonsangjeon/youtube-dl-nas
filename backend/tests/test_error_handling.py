"""Tests for error handling and input validation."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.ytdlp_service import build_download_cmd


async def _get_auth_headers(client: AsyncClient) -> dict:
    resp = await client.post("/api/auth/login", json={"id": "admin", "pw": "admin"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_invalid_url_rejected() -> None:
    """Invalid URL should return 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _get_auth_headers(client)
        response = await client.post(
            "/api/downloads",
            json={"url": "not-a-url", "resolution": "best"},
            headers=headers,
        )
    assert response.status_code == 400


def test_invalid_subtitle_resolution_empty_lang() -> None:
    """Subtitle resolution without language should raise ValueError."""
    with pytest.raises(ValueError, match="Subtitle resolution must be"):
        build_download_cmd("https://example.com/video", "srt|")


def test_invalid_subtitle_resolution_no_separator() -> None:
    """Subtitle resolution without | separator should raise ValueError."""
    with pytest.raises(ValueError, match="Subtitle resolution must be"):
        build_download_cmd("https://example.com/video", "srt")


def test_valid_subtitle_resolution() -> None:
    """Valid subtitle resolution should not raise."""
    cmd = build_download_cmd("https://example.com/video", "srt|en")
    assert "--write-auto-subs" in cmd
    assert "en" in cmd

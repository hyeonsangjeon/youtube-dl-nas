"""Tests for legacy REST API endpoint (POST /youtube-dl/rest)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@patch("app.routers.legacy.download_manager")
async def test_legacy_download_success(mock_dm) -> None:
    """Valid credentials should enqueue and return v1 success format."""
    mock_dm.enqueue = AsyncMock(return_value="fake-id")
    mock_dm.get_queue_size = AsyncMock(return_value=0)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/youtube-dl/rest",
            json={"url": "https://example.com/video", "resolution": "best", "id": "admin", "pw": "admin"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["msg"] == "download has started"
    assert "Remaining downloading count" in data
    mock_dm.enqueue.assert_awaited_once_with("https://example.com/video", "best")


@pytest.mark.asyncio
async def test_legacy_download_invalid_credentials() -> None:
    """Wrong credentials should return 200 with v1 failure format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/youtube-dl/rest",
            json={"url": "https://example.com/video", "id": "wrong", "pw": "wrong"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["msg"] == "Invalid password or account."


@pytest.mark.asyncio
@patch("app.routers.legacy.download_manager")
async def test_legacy_response_key_names(mock_dm) -> None:
    """Response must use exact v1 key names including spaces."""
    mock_dm.enqueue = AsyncMock(return_value="fake-id")
    mock_dm.get_queue_size = AsyncMock(return_value=2)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/youtube-dl/rest",
            json={"url": "https://example.com/video", "id": "admin", "pw": "admin"},
        )
    data = response.json()
    # Exact key names from v1 — "Remaining downloading count" with spaces
    assert set(data.keys()) == {"success", "msg", "Remaining downloading count"}
    assert data["Remaining downloading count"] == "2"

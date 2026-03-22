"""Tests for v2 download API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _get_auth_headers(client: AsyncClient) -> dict:
    """Helper to get JWT auth headers."""
    resp = await client.post(
        "/api/auth/login",
        json={"id": "admin", "pw": "admin"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_download() -> None:
    """POST /api/downloads with valid JWT should enqueue and return 201."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _get_auth_headers(client)
        response = await client.post(
            "/api/downloads",
            json={"url": "https://example.com/video", "resolution": "best"},
            headers=headers,
        )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "queued"
    assert data["url"] == "https://example.com/video"


@pytest.mark.asyncio
async def test_create_download_no_auth() -> None:
    """POST /api/downloads without JWT should return 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/downloads",
            json={"url": "https://example.com/video"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_history() -> None:
    """GET /api/downloads/history with JWT should return paginated list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _get_auth_headers(client)
        response = await client.get("/api/downloads/history", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_delete_history_not_found() -> None:
    """DELETE nonexistent download should return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _get_auth_headers(client)
        response = await client.delete(
            "/api/downloads/history/nonexistent-id",
            headers=headers,
        )
    assert response.status_code == 404

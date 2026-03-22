"""Tests for file serving endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _get_auth_headers(client: AsyncClient) -> dict:
    resp = await client.post("/api/auth/login", json={"id": "admin", "pw": "admin"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_serve_file_not_found() -> None:
    """Non-existent download ID should return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _get_auth_headers(client)
        response = await client.get(
            "/api/files/nonexistent-uuid",
            headers=headers,
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_serve_file_no_auth() -> None:
    """File serving without JWT should be rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/files/some-uuid")
    # HTTPBearer returns 403 when no token is provided
    assert response.status_code == 401

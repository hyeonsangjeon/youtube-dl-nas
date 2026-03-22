"""Tests for authentication endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_login_success() -> None:
    """Valid credentials should return access + refresh tokens."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"id": "admin", "pw": "admin"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password() -> None:
    """Wrong password should return 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"id": "admin", "pw": "wrongpassword"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_id() -> None:
    """Wrong ID should return 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"id": "wronguser", "pw": "admin"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token() -> None:
    """Valid refresh token should return new access token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post(
            "/api/auth/login",
            json={"id": "admin", "pw": "admin"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        refresh_resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails() -> None:
    """Using access token as refresh token should fail."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post(
            "/api/auth/login",
            json={"id": "admin", "pw": "admin"},
        )
        access_token = login_resp.json()["access_token"]

        refresh_resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token},
        )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_without_token() -> None:
    """Health check should work without authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200

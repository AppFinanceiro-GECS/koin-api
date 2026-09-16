import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials returns 401"""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "WrongPass123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient):
    """Test login with missing fields returns 422"""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            # password missing
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_invite_token(client: AsyncClient):
    """Test accessing invalid invite token returns 404"""
    response = await client.get("/api/v1/auth/invite/invalid-token")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health endpoint returns ok"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

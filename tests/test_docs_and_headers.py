"""Testes do Swagger fechado em produção e dos cabeçalhos HTTP (issue #51)."""

import os
import subprocess
import sys

import pytest
from httpx import AsyncClient

PROBE = """
import asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        codes = [(await c.get(p)).status_code for p in ("/docs", "/redoc", "/openapi.json", "/health")]
        print(*codes)

asyncio.run(main())
"""


def _probe_docs(environment: str) -> list[int]:
    # O app lê ENVIRONMENT ao ser importado, então cada ambiente roda num processo próprio.
    env = {**os.environ, "ENVIRONMENT": environment, "DATABASE_URL": "sqlite+aiosqlite:///:memory:"}
    result = subprocess.run(
        [sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, check=True
    )
    return [int(code) for code in result.stdout.split()[-4:]]


def test_docs_are_closed_in_production():
    assert _probe_docs("production") == [404, 404, 404, 200]


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_docs_stay_open_outside_production(environment):
    assert _probe_docs(environment) == [200, 200, 200, 200]


@pytest.mark.asyncio
async def test_api_responses_have_hardening_headers(client: AsyncClient):
    response = await client.get("/api/v1/auth/invite/invalid-token")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "0"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_swagger_page_is_not_cached_nor_blocked_by_csp(client: AsyncClient):
    response = await client.get("/docs")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    assert "Cache-Control" not in response.headers

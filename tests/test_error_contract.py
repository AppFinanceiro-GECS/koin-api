"""
#41: erro no formato problem+json com code estável e request_id; versão exposta.
#27: X-Request-ID, /health com banco e /health/live.
"""

import logging
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.errors import PROBLEM_JSON, register_error_handlers
from app.core.request_context import RequestContextMiddleware, RequestIdLogFilter, request_id_var

PYPROJECT_VERSION = tomllib.loads(
    (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]


def _assert_problem(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == "about:blank"
    assert body["title"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


async def test_rota_inexistente(client):
    body = _assert_problem(await client.get("/api/v1/nao-existe"), 404, "not_found")
    assert body["detail"] == "Recurso não encontrado"


async def test_sem_token_e_401_em_portugues(client):
    response = await client.get("/api/v1/auth/me")
    body = _assert_problem(response, 401, "not_authenticated")
    assert body["detail"] == "Não autenticado"


async def test_validacao_mantem_detail_e_lista_campos(client):
    response = await client.post("/api/v1/auth/login", json={"email": "invalido"})
    body = _assert_problem(response, 422, "validation_error")
    # o koin-app lê detail[0].msg
    assert isinstance(body["detail"], list) and body["detail"][0]["msg"]
    fields = {e["field"] for e in body["errors"]}
    assert "body.email" in fields
    assert "body.password" in fields


async def test_detail_de_rota_continua_igual(client, test_user, db_session):
    await db_session.commit()
    response = await client.post(
        "/api/v1/auth/login", json={"email": "test@example.com", "password": "errada123"}
    )
    body = _assert_problem(response, 401, "not_authenticated")
    assert body["detail"] == "Email ou senha incorretos"


def _mini_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/explode")
    async def explode():
        raise RuntimeError("segredo interno do banco")

    @app.get("/limite")
    async def limite():
        raise HTTPException(429, detail={"error": "plan_limit_reached", "message": "Limite"})

    return app


async def _mini_client():
    transport = ASGITransport(app=_mini_app(), raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_500_vira_json_com_id_e_sem_vazar_excecao():
    async with await _mini_client() as client:
        response = await client.get("/explode")
    body = _assert_problem(response, 500, "internal_error")
    assert body["request_id"] in body["detail"]
    assert "segredo" not in response.text


async def test_code_da_rota_e_preservado():
    async with await _mini_client() as client:
        response = await client.get("/limite")
    body = _assert_problem(response, 429, "plan_limit_reached")
    assert body["detail"]["message"] == "Limite"


async def test_request_id_do_cliente_e_propagado(client):
    response = await client.get("/health/live", headers={"X-Request-ID": "app-123.abc"})
    assert response.headers["X-Request-ID"] == "app-123.abc"


@pytest.mark.parametrize("bad", ["com espaco", "x" * 65, "quebra\\nlinha", "a;b"])
async def test_request_id_invalido_e_substituido(client, bad):
    response = await client.get("/health/live", headers={"X-Request-ID": bad})
    assert response.headers["X-Request-ID"] != bad
    assert len(response.headers["X-Request-ID"]) == 32


async def test_versao_em_health_header_e_openapi(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "ok"
    assert body["version"] == PYPROJECT_VERSION
    assert body["commit"]
    assert response.headers["X-API-Version"] == PYPROJECT_VERSION
    openapi = (await client.get("/openapi.json")).json()
    assert openapi["info"]["version"] == PYPROJECT_VERSION


async def test_health_503_quando_o_banco_cai(client, monkeypatch):
    import app.main as main

    class Broken:
        def connect(self):
            raise ConnectionError("db down")

    monkeypatch.setattr(main, "engine", Broken())
    response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["db"] == "error"
    # liveness não depende do banco: o Docker não reinicia a API à toa
    assert (await client.get("/health/live")).status_code == 200


def test_log_recebe_o_request_id():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    token = request_id_var.set("abc123")
    try:
        RequestIdLogFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "abc123"

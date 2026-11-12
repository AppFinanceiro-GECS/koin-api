"""Swagger fechado em produção e cabeçalhos de segurança (#51)."""

from app.main import docs_urls


def test_swagger_fechado_em_producao():
    assert docs_urls("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_swagger_aberto_na_hml_e_em_desenvolvimento():
    for env in ("staging", "development"):
        assert docs_urls(env)["openapi_url"] == "/openapi.json"


async def test_cabecalhos_de_seguranca(client):
    response = await client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-XSS-Protection" not in response.headers

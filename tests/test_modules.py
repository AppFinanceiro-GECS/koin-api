"""
#42: ENABLED_MODULES liga e desliga rotas e jobs sem apagar código.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import modules as modules_mod
from app.core import scheduler as scheduler_mod
from app.core.modules import ALL_MODULES, ALWAYS_ON, MVP_MODULES, parse_modules
from app.routers import ROUTES, build_api_router


def test_padrao_liga_tudo():
    assert parse_modules(None) == ALL_MODULES
    assert parse_modules("") == ALL_MODULES
    assert parse_modules("all") == ALL_MODULES


def test_mvp_e_lista_combinada():
    assert parse_modules("mvp") == MVP_MODULES
    assert parse_modules("mvp, goals") == MVP_MODULES | {"goals"}
    assert parse_modules("transactions") == ALWAYS_ON | {"transactions"}


def test_nome_desconhecido_falha_na_inicializacao():
    with pytest.raises(ValueError, match="grocerie"):
        parse_modules("mvp,grocerie")


def test_registro_cobre_todos_os_modulos():
    assert {module for module, *_ in ROUTES} == set(ALL_MODULES)
    assert {module for module, *_ in scheduler_mod.JOBS} <= set(ALL_MODULES)


def _paths(modules) -> set[str]:
    app = FastAPI()
    app.include_router(build_api_router(modules))
    return set(app.openapi()["paths"])


def test_mvp_nao_registra_rotas_fora_do_mvp():
    paths = _paths(MVP_MODULES)
    assert any(p.startswith("/transactions") for p in paths)
    assert any(p.startswith("/invoices") for p in paths)
    for hidden in ("/grocery", "/gamification", "/chat", "/debts", "/automations"):
        assert not any(p.startswith(hidden) for p in paths), hidden


async def test_rota_desligada_responde_404():
    app = FastAPI()
    app.include_router(build_api_router(MVP_MODULES), prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/grocery/lists")).status_code == 404
        # rota do MVP existe (sem token → não é 404)
        assert (await client.get("/api/v1/transactions")).status_code != 404


def test_jobs_seguem_os_modulos(monkeypatch):
    added = []
    monkeypatch.setattr(scheduler_mod, "enabled_modules", lambda: MVP_MODULES)
    monkeypatch.setattr(
        scheduler_mod.scheduler, "add_job", lambda func, trigger, id, **kw: added.append(id)
    )

    scheduler_mod.register_jobs()

    assert "generate_recurring_transactions" in added
    assert "check_invoice_due_dates" in added
    assert "process_scheduled_automations" not in added
    assert "check_goal_milestones" not in added


async def test_health_lista_modulos(client, monkeypatch):
    monkeypatch.setattr(modules_mod.settings, "enabled_modules", "mvp")
    response = await client.get("/health")
    assert response.json()["modules"] == sorted(MVP_MODULES)

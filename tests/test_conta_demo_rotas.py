"""
#40: as rotas do núcleo do MVP sobre uma conta com histórico real (o seed de
demonstração: 2 cartões, 3 meses, parcelas, recorrentes e fatura paga).

Pega 500 em consulta e filtro (o que derrubou o GET /transactions no #33) e confere
os efeitos de editar, excluir, transferir e confirmar em lote.
"""

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.core.utils import today_br
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.transaction import Transaction
from app.modules.auth.services.user_setup import setup_new_user

API = "/api/v1"


def _seed_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def demo(client, test_user, db_session):
    await setup_new_user(db_session, test_user.id)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"
    await _seed_module().Seeder(client).run()
    return client


async def _ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if "json" in response.headers.get("content-type", "") else response


async def _cards(api) -> dict[str, dict]:
    return {c["name"]: c for c in await _ok(await api.get(f"{API}/credit-cards"))}


async def _bank(api) -> dict:
    return next(a for a in await _ok(await api.get(f"{API}/accounts")) if a["name"] == "Banco")


async def _invoice_total(db_session, invoice_id) -> float:
    invoice = await db_session.get(CreditCardInvoice, invoice_id)
    await db_session.refresh(invoice)
    return float(invoice.total_amount)


# ---------- consultas ----------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"type": "expense"},
        {"type": "income"},
        {"search": "Netflix"},
        {"limit": 100, "offset": 10},
    ],
)
async def test_listar_transacoes_com_filtros(demo, params):
    page = await _ok(await demo.get(f"{API}/transactions", params=params))
    assert "items" in page
    if params.get("search"):
        assert page["items"] and all("Netflix" in i["description"] for i in page["items"])
    if params.get("type"):
        assert all(i["type"] == params["type"] for i in page["items"])


async def test_listar_por_periodo_conta_e_categoria(demo):
    today = today_br()
    bank = await _bank(demo)
    start = (today - timedelta(days=95)).isoformat()
    page = await _ok(
        await demo.get(
            f"{API}/transactions",
            params={"start_date": start, "end_date": today.isoformat(), "account_id": bank["id"]},
        )
    )
    assert page["items"] and all(i["account_id"] == bank["id"] for i in page["items"])

    category_id = page["items"][0]["category_id"]
    by_category = await _ok(
        await demo.get(f"{API}/transactions", params={"category_id": category_id})
    )
    assert all(i["category_id"] == category_id for i in by_category["items"])


async def test_exportar_csv(demo):
    response = await demo.get(f"{API}/transactions/export/csv")
    assert response.status_code == 200
    assert "csv" in response.headers["content-type"]
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) > 30  # cabeçalho + 3 meses de lançamentos


async def test_faturas_visao_geral_e_detalhe(demo):
    today = today_br()
    cards = await _cards(demo)
    nubank = cards["Nubank Roxinho"]

    invoices = await _ok(await demo.get(f"{API}/invoices", params={"credit_card_id": nubank["id"]}))
    assert invoices and all(i["credit_card_id"] == nubank["id"] for i in invoices)
    paid = [i for i in invoices if i["status"] == "paid"]
    assert len(paid) == 1

    for status in ("open", "paid"):
        filtered = await _ok(await demo.get(f"{API}/invoices", params={"status": status}))
        assert all(i["status"] == status for i in filtered)

    overview = await _ok(
        await demo.get(
            f"{API}/invoices/overview", params={"year": today.year, "month": today.month}
        )
    )
    assert overview is not None

    detail = await _ok(await demo.get(f"{API}/invoices/{invoices[0]['id']}"))
    assert detail["id"] == invoices[0]["id"]
    await _ok(await demo.get(f"{API}/invoices/{invoices[0]['id']}/duplicate-warnings"))
    by_card = await _ok(await demo.get(f"{API}/invoices/credit-card/{nubank['id']}"))
    assert {i["id"] for i in by_card} <= {i["id"] for i in invoices}
    await _ok(await demo.get(f"{API}/invoices/credit-card/{nubank['id']}/current"))


async def test_parcelamentos(demo):
    series = await _ok(await demo.get(f"{API}/installments"))
    assert {s["installment_count"] for s in series} == {10, 3}
    for s in series:
        detail = await _ok(await demo.get(f"{API}/installments/{s['id']}"))
        assert detail["id"] == s["id"]
    groups = await _ok(await demo.post(f"{API}/installments/detect-duplicates"))
    assert groups is not None
    await _ok(await demo.post(f"{API}/installments/detect-transaction-duplicates"))


async def test_analytics_do_mes_e_do_periodo(demo):
    today = today_br()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    summary = await _ok(
        await demo.get(f"{API}/analytics/summary", params={"year": year, "month": month})
    )
    assert summary["total_income"] == pytest.approx(6200)
    assert summary["total_expense"] > 0
    assert summary["credit_card_expenses"] > 0

    period = {"start_date": (today - timedelta(days=90)).isoformat(), "end_date": today.isoformat()}
    await _ok(await demo.get(f"{API}/analytics/insights", params=period))
    report = await _ok(await demo.get(f"{API}/analytics/by-payment-method", params=period))
    assert report is not None


# ---------- escrita ----------


async def test_editar_compra_atualiza_a_fatura(demo, db_session):
    nubank = (await _cards(demo))["Nubank Roxinho"]
    tx = await _ok(
        await demo.post(
            f"{API}/transactions",
            json={
                "description": "Livraria",
                "amount": "50.00",
                "date": today_br().isoformat(),
                "type": "expense",
                "account_id": nubank["account_id"],
                "credit_card_id": nubank["id"],
            },
        ),
        201,
    )
    before = await _invoice_total(db_session, tx["invoice_id"])

    updated = await _ok(
        await demo.patch(f"{API}/transactions/{tx['id']}", json={"amount": "80.00"})
    )
    assert float(updated["amount"]) == 80.0
    assert await _invoice_total(db_session, tx["invoice_id"]) == pytest.approx(before + 30)

    await _ok(await demo.delete(f"{API}/transactions/{tx['id']}"))
    assert await _invoice_total(db_session, tx["invoice_id"]) == pytest.approx(before - 50)
    assert (await demo.get(f"{API}/transactions/{tx['id']}")).status_code == 404


async def test_excluir_serie_de_parcelas(demo, db_session):
    series = next(
        s for s in await _ok(await demo.get(f"{API}/installments")) if s["installment_count"] == 3
    )
    first = await db_session.scalar(
        select(Transaction.id).where(Transaction.installment_series_id == series["id"]).limit(1)
    )

    await _ok(await demo.delete(f"{API}/transactions/{first}", params={"delete_series": True}))

    remaining = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.installment_series_id == series["id"])
    )
    assert remaining == 0


async def test_transferencia_entre_contas(demo):
    """Saldo calculado pela API (inicial + lançamentos), o mesmo que o app mostra."""

    async def balances():
        return {a["name"]: a["balance"] for a in await _ok(await demo.get(f"{API}/accounts"))}

    accounts = {a["name"]: a for a in await _ok(await demo.get(f"{API}/accounts"))}
    before = await balances()

    await _ok(
        await demo.post(
            f"{API}/transactions",
            json={
                "description": "Saque",
                "amount": "200.00",
                "date": today_br().isoformat(),
                "type": "transfer",
                "account_id": accounts["Banco"]["id"],
                "destination_account_id": accounts["Carteira"]["id"],
            },
        ),
        201,
    )

    after = await balances()
    assert after["Banco"] == pytest.approx(before["Banco"] - 200)
    assert after["Carteira"] == pytest.approx(before["Carteira"] + 200)


async def test_confirmar_em_lote(demo, db_session):
    itau = (await _cards(demo))["Itaú Click"]
    day = today_br().isoformat()
    result = await _ok(
        await demo.post(
            f"{API}/transactions/batch-confirm",
            json={
                "items": [
                    {
                        "account_id": itau["account_id"],
                        "credit_card_id": itau["id"],
                        "amount": "19.90",
                        "date": day,
                        "description": "Café",
                    },
                    {
                        "account_id": itau["account_id"],
                        "credit_card_id": itau["id"],
                        "amount": "64.00",
                        "date": day,
                        "description": "Cinema",
                    },
                ]
            },
        ),
        201,
    )
    assert result is not None
    count = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.description.in_(["Café", "Cinema"]))
    )
    assert count == 2


async def test_conferir_parcela_projetada(demo):
    itau = (await _cards(demo))["Itaú Click"]
    response = await _ok(
        await demo.post(
            f"{API}/transactions/check-projected",
            json={
                "items": [{"index": 0, "description": "Notebook Dell", "amount": 420.0}],
                "credit_card_id": itau["id"],
            },
        )
    )
    assert response is not None


async def test_fatura_manual_editar_e_excluir(demo):
    itau = (await _cards(demo))["Itaú Click"]
    future = today_br() + timedelta(days=400)

    invoice = await _ok(
        await demo.post(
            f"{API}/invoices",
            json={
                "credit_card_id": itau["id"],
                "reference_month": future.month,
                "reference_year": future.year,
            },
        ),
        201,
    )
    duplicate = await demo.post(
        f"{API}/invoices",
        json={
            "credit_card_id": itau["id"],
            "reference_month": future.month,
            "reference_year": future.year,
        },
    )
    assert duplicate.status_code == 409

    edited = await _ok(
        await demo.patch(f"{API}/invoices/{invoice['id']}", json={"notes": "conferir"})
    )
    assert edited["notes"] == "conferir"
    await _ok(await demo.delete(f"{API}/invoices/{invoice['id']}"))
    assert (await demo.get(f"{API}/invoices/{invoice['id']}")).status_code == 404


async def test_projetar_futuro_e_reprocessar_orfas(demo):
    itau = (await _cards(demo))["Itaú Click"]
    await _ok(
        await demo.post(f"{API}/invoices/project-future", json={"credit_card_id": itau["id"]})
    )
    await _ok(await demo.post(f"{API}/invoices/reprocess-orphan-transactions"))


async def test_outro_usuario_nao_ve_os_dados(demo, db_session):
    from app.core.security import get_password_hash
    from app.models.user import User

    other = User(
        email="outro@example.com", name="Outro", hashed_password=get_password_hash("x" * 8)
    )
    db_session.add(other)
    await db_session.commit()
    invoice_id = (await _ok(await demo.get(f"{API}/invoices")))[0]["id"]
    tx_id = (await _ok(await demo.get(f"{API}/transactions")))["items"][0]["id"]

    demo.headers["Authorization"] = f"Bearer {create_access_token(other.id)}"
    assert (await demo.get(f"{API}/invoices/{invoice_id}")).status_code == 404
    assert (await demo.get(f"{API}/transactions/{tx_id}")).status_code == 404
    assert (await _ok(await demo.get(f"{API}/transactions")))["items"] == []


def test_datas_do_seed_cobrem_tres_meses():
    seed = _seed_module()
    assert seed.months_back(date(2026, 3, 1), 2) == (2026, 1)

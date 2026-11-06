"""
#40: critérios de aceite do MVP pela API, do jeito que o app usa.

Cada teste cita a regra do docs/business/LOGIC_MAP.md que protege. Rodam em SQLite
e, no CI, também em Postgres (#28), onde aparecem os bugs de lazy-load (#33).
"""

from datetime import date, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.modules.auth.services.user_setup import setup_new_user
from app.modules.notifications.services.alert_engine import AlertEngine

API = "/api/v1"


@pytest.fixture
async def api(client, test_user, db_session):
    """Cliente autenticado com as contas e categorias padrão do cadastro."""
    await setup_new_user(db_session, test_user.id)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"
    return client


async def _ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


async def _bank(api) -> dict:
    accounts = await _ok(await api.get(f"{API}/accounts"))
    return next(a for a in accounts if a["name"] == "Banco")


async def _category(api, name, kind="expense") -> int:
    categories = await _ok(await api.get(f"{API}/categories"))
    return next(c["id"] for c in categories if c["name"] == name and c["type"] == kind)


async def _card(api, closing=10, due=17, limit=5000, name="Nubank") -> dict:
    return await _ok(
        await api.post(
            f"{API}/credit-cards",
            json={"name": name, "credit_limit": limit, "closing_day": closing, "due_day": due},
        ),
        201,
    )


async def _purchase(api, card, amount, when, description="Compra", **extra) -> dict:
    return await _ok(
        await api.post(
            f"{API}/transactions",
            json={
                "description": description,
                "amount": str(amount),
                "date": when.isoformat(),
                "type": "expense",
                "account_id": card["account_id"],
                "credit_card_id": card["id"],
                **extra,
            },
        ),
        201,
    )


async def _invoice_of(db_session, tx_id) -> CreditCardInvoice:
    tx = await db_session.get(Transaction, tx_id)
    await db_session.refresh(tx)
    return await db_session.get(CreditCardInvoice, tx.invoice_id)


# ---------- RN003: compra depois do fechamento vai para a fatura seguinte ----------


@pytest.mark.parametrize(
    "closing,purchase,expected",
    [
        (10, date(2026, 3, 10), (3, 2026)),  # no dia do fechamento: fatura do mês
        (10, date(2026, 3, 11), (4, 2026)),  # depois do fechamento: mês seguinte
        (10, date(2026, 12, 20), (1, 2027)),  # virada do ano
        (31, date(2026, 4, 30), (4, 2026)),  # fecha "dia 31" em mês de 30 dias
        (30, date(2027, 2, 28), (2, 2027)),  # fevereiro curto
    ],
)
async def test_rn003_mes_da_fatura(api, db_session, closing, purchase, expected):
    card = await _card(api, closing=closing, due=5)
    tx = await _purchase(api, card, "50.00", purchase)

    invoice = await _invoice_of(db_session, tx["id"])

    assert (invoice.reference_month, invoice.reference_year) == expected
    last_day = (date(expected[1], expected[0], 28) + timedelta(days=4)).replace(day=1) - timedelta(
        days=1
    )
    assert invoice.closing_date == date(expected[1], expected[0], min(closing, last_day.day))
    # vencimento antes do fechamento: cai no mês seguinte ao fechamento
    assert invoice.due_date > invoice.closing_date


async def test_rn003_total_da_fatura_soma_as_compras(api, db_session):
    card = await _card(api)
    first = await _purchase(api, card, "100.00", date(2026, 5, 2))
    await _purchase(api, card, "23.45", date(2026, 5, 9))

    invoice = await _invoice_of(db_session, first["id"])
    await db_session.refresh(invoice)

    assert float(invoice.total_amount) == pytest.approx(123.45)


# ---------- RN006 e RN010: pagamento de fatura ----------


async def test_rn006_pagamento_com_cartao_e_recusado(api, db_session):
    card = await _card(api)
    other = await _card(api, name="Itaú")
    tx = await _purchase(api, card, "80.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    response = await api.post(
        f"{API}/invoices/{invoice.id}/pay",
        json={"amount": 80, "payment_account_id": other["account_id"]},
    )

    assert response.status_code == 400
    assert "cartão" in response.json()["detail"]


async def test_rn010_pagamento_parcial_e_depois_total(api, db_session):
    bank = await _bank(api)
    card = await _card(api)
    tx = await _purchase(api, card, "300.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    partial = await _ok(
        await api.post(
            f"{API}/invoices/{invoice.id}/pay",
            json={"amount": 100, "payment_account_id": bank["id"], "payment_method": "pix"},
        )
    )
    assert partial["status"] == "partial"

    paid = await _ok(
        await api.post(
            f"{API}/invoices/{invoice.id}/pay",
            json={"amount": 200, "payment_account_id": bank["id"]},
        )
    )
    assert paid["status"] == "paid"

    again = await api.post(
        f"{API}/invoices/{invoice.id}/pay", json={"amount": 1, "payment_account_id": bank["id"]}
    )
    assert again.status_code == 400


# ---------- RN005: parcelas projetadas, sem duplicar ----------


async def test_rn005_parcelas_futuras_uma_por_fatura(api, db_session):
    card = await _card(api)
    first = await _purchase(
        api,
        card,
        "150.00",
        date(2026, 5, 2),
        description="Geladeira",
        is_installment=True,
        installment_current=1,
        installment_total=6,
        create_future_installments=True,
    )

    series_id = (await db_session.get(Transaction, first["id"])).installment_series_id
    rows = (
        await db_session.execute(
            select(Transaction.installment_number, Transaction.invoice_id).where(
                Transaction.installment_series_id == series_id
            )
        )
    ).all()

    assert sorted(n for n, _ in rows) == [1, 2, 3, 4, 5, 6]
    # cada parcela numa fatura diferente
    assert len({invoice for _, invoice in rows}) == 6

    series = await _ok(await api.get(f"{API}/installments/{series_id}"))
    assert series["installment_count"] == 6


async def test_rn005_lancar_parcela_existente_nao_duplica(api, db_session):
    card = await _card(api)
    first = await _purchase(
        api,
        card,
        "150.00",
        date(2026, 5, 2),
        description="Geladeira",
        is_installment=True,
        installment_current=1,
        installment_total=6,
        create_future_installments=True,
    )
    series_id = (await db_session.get(Transaction, first["id"])).installment_series_id

    # a parcela 2 chega de novo (ex.: lida da fatura seguinte)
    await api.post(
        f"{API}/transactions",
        json={
            "description": "Geladeira",
            "amount": "150.00",
            "date": date(2026, 6, 2).isoformat(),
            "type": "expense",
            "account_id": card["account_id"],
            "credit_card_id": card["id"],
            "is_installment": True,
            "installment_current": 2,
            "installment_total": 6,
            "installment_series_id": series_id,
        },
    )

    count = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.installment_series_id == series_id, Transaction.installment_number == 2)
    )
    assert count == 1


# ---------- RN008: resumo do mês não conta pagamento de fatura como despesa ----------


async def test_rn008_pagamento_de_fatura_fora_das_despesas(api, db_session):
    bank = await _bank(api)
    card = await _card(api)
    when = date(2026, 5, 2)
    await _ok(
        await api.post(
            f"{API}/transactions",
            json={
                "description": "Salário",
                "amount": "5000.00",
                "date": when.isoformat(),
                "type": "income",
                "account_id": bank["id"],
                "category_id": await _category(api, "Salário", "income"),
            },
        ),
        201,
    )
    tx = await _purchase(
        api, card, "400.00", when, category_id=await _category(api, "Supermercado")
    )
    invoice = await _invoice_of(db_session, tx["id"])
    await _ok(
        await api.post(
            f"{API}/invoices/{invoice.id}/pay",
            json={"amount": 400, "payment_account_id": bank["id"], "payment_date": "2026-05-20"},
        )
    )

    summary = await _ok(
        await api.get(f"{API}/analytics/summary", params={"year": 2026, "month": 5})
    )

    assert summary["total_income"] == pytest.approx(5000)
    # a compra conta uma vez; o pagamento da fatura não é outra despesa
    assert summary["total_expense"] == pytest.approx(400)


# ---------- Listagem: regressão do 500 com compra no cartão (#33) ----------


async def test_listagem_com_cartao_categoria_e_fatura(api):
    card = await _card(api, name="Nubank Roxinho")
    supermercado = await _category(api, "Supermercado")
    await _purchase(api, card, "42.00", date(2026, 5, 2), category_id=supermercado)

    page = await _ok(await api.get(f"{API}/transactions"))

    item = page["items"][0]
    assert item["credit_card_name"] == "Nubank Roxinho"
    assert item["category_name"] == "Supermercado"
    assert item["invoice_id"]

    detail = await _ok(await api.get(f"{API}/transactions/{item['id']}"))
    assert detail["credit_card_name"] == "Nubank Roxinho"


# ---------- Upload → extração (IA simulada) → confirmação ----------


async def test_upload_extracao_confirmacao(api, db_session, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.modules.documents.services.llm_ocr_service import LLMOCRService

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mistral_api_key", None)

    async def fake_extract(self, *args, **kwargs):
        return {
            "document_type": "fatura_cartao",
            "card_info": {"total_amount": 155.0},
            "items": [
                {"description": "PADARIA CENTRAL", "amount": 35.0, "date": "2026-05-03"},
                {"description": "POSTO SHELL", "amount": 120.0, "date": "2026-05-04"},
            ],
        }

    monkeypatch.setattr(LLMOCRService, "extract_from_image", fake_extract)
    card = await _card(api)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    document = await _ok(
        await api.post(f"{API}/documents", files={"file": ("fatura.png", png, "image/png")}),
        201,
    )
    assert document["status"] == "completed"
    assert [i["description"] for i in document["extracted_items"]] == [
        "PADARIA CENTRAL",
        "POSTO SHELL",
    ]

    confirmed = []
    for item in document["extracted_items"]:
        confirmed.append(
            await _ok(
                await api.post(
                    f"{API}/transactions/confirm",
                    json={
                        "document_id": document["id"],
                        "account_id": card["account_id"],
                        "credit_card_id": card["id"],
                        "amount": item["amount"],
                        "date": item["date"] or "2026-05-03",
                        "description": item["description"],
                    },
                ),
                201,
            )
        )

    linked = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.document_id == document["id"])
    )
    assert linked == 2
    invoice = await _invoice_of(db_session, confirmed[0]["id"])
    await db_session.refresh(invoice)
    assert float(invoice.total_amount) == pytest.approx(155.0)


# ---------- Alertas (alert_engine) com data congelada ----------


async def _notifications(db_session, user_id, kind=None) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if kind:
        query = query.where(Notification.type == kind)
    return list((await db_session.execute(query)).scalars())


@pytest.mark.parametrize(
    "days,kind", [(7, "invoice_due_7_days"), (3, "invoice_due_3_days"), (1, "invoice_due_1_day")]
)
async def test_alerta_de_vencimento(api, db_session, test_user, days, kind):
    card = await _card(api, closing=10, due=17)
    tx = await _purchase(api, card, "90.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    # meio-dia: data pura congela à meia-noite UTC, que ainda é o dia anterior em Brasília
    with freeze_time(f"{invoice.due_date - timedelta(days=days)} 12:00"):
        created = await AlertEngine(db_session).check_invoice_due_dates(test_user)
        # rodar de novo no mesmo dia não repete o aviso
        again = await AlertEngine(db_session).check_invoice_due_dates(test_user)
    await db_session.commit()

    assert created == 1 and again == 0
    assert len(await _notifications(db_session, test_user.id, kind)) == 1


async def test_alerta_de_fatura_vencida(api, db_session, test_user):
    card = await _card(api)
    tx = await _purchase(api, card, "90.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    with freeze_time(f"{invoice.due_date + timedelta(days=2)} 12:00"):
        assert await AlertEngine(db_session).check_invoice_due_dates(test_user) == 1
    await db_session.commit()

    assert len(await _notifications(db_session, test_user.id, "invoice_overdue")) == 1


async def test_alerta_de_limite_com_parcelas_em_varias_faturas(api, db_session, test_user):
    """Cartão com parcelamento tem várias faturas abertas ao mesmo tempo."""
    card = await _card(api, limit=1000)
    await _purchase(
        api,
        card,
        "300.00",
        date(2026, 5, 2),
        is_installment=True,
        installment_current=1,
        installment_total=3,
        create_future_installments=True,
    )

    with freeze_time("2026-05-05 12:00"):
        created = await AlertEngine(db_session).check_credit_card_limits(test_user)
    await db_session.commit()

    assert created == 1
    assert len(await _notifications(db_session, test_user.id, "credit_limit_80")) == 1


async def test_rodar_todos_os_alertas_nao_quebra(api, db_session, test_user):
    card = await _card(api)
    await _purchase(api, card, "90.00", date(2026, 5, 2))

    with freeze_time("2026-05-14 12:00"):
        await AlertEngine(db_session).check_all_alerts_for_user(test_user)


async def test_lembrete_dispara_com_a_fatura_ja_fechada(api, db_session, test_user):
    """O GET /invoices fecha a fatura depois do fechamento; o lembrete de D-3 vem depois."""
    card = await _card(api, closing=10, due=17)
    tx = await _purchase(api, card, "90.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    with freeze_time(f"{invoice.due_date - timedelta(days=3)} 12:00"):
        await _ok(await api.get(f"{API}/invoices"))
        await db_session.refresh(invoice)
        assert invoice.status == "closed"
        assert await AlertEngine(db_session).check_invoice_due_dates(test_user) == 1
    await db_session.commit()

    assert len(await _notifications(db_session, test_user.id, "invoice_due_3_days")) == 1


async def test_aviso_de_vencida_com_status_overdue(api, db_session, test_user):
    card = await _card(api, closing=10, due=17)
    tx = await _purchase(api, card, "90.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])

    with freeze_time(f"{invoice.due_date + timedelta(days=1)} 12:00"):
        await _ok(await api.get(f"{API}/invoices"))  # open -> closed
        await _ok(await api.get(f"{API}/invoices"))  # closed -> overdue
        await db_session.refresh(invoice)
        assert invoice.status == "overdue"
        assert await AlertEngine(db_session).check_invoice_due_dates(test_user) == 1


async def test_fatura_paga_nao_gera_lembrete(api, db_session, test_user):
    bank = await _bank(api)
    card = await _card(api, closing=10, due=17)
    tx = await _purchase(api, card, "90.00", date(2026, 5, 2))
    invoice = await _invoice_of(db_session, tx["id"])
    await _ok(
        await api.post(
            f"{API}/invoices/{invoice.id}/pay",
            json={"amount": 90, "payment_account_id": bank["id"]},
        )
    )

    with freeze_time(f"{invoice.due_date - timedelta(days=3)} 12:00"):
        assert await AlertEngine(db_session).check_invoice_due_dates(test_user) == 0

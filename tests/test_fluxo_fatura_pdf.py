"""
#40: o caminho da fatura em PDF depois da leitura — identificar o cartão, criar a fatura
do documento e confirmar compras parceladas sem duplicar as parcelas já projetadas
(RN005). A IA não entra aqui: os dados extraídos vão direto na requisição.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.document import Document, DocumentStatus
from app.models.installment import InstallmentSeries
from app.models.transaction import Transaction
from app.modules.auth.services.user_setup import setup_new_user

API = "/api/v1"


@pytest.fixture
async def api(client, test_user, db_session):
    await setup_new_user(db_session, test_user.id)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"
    return client


async def _ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


async def _card(api, name, last4, closing=3, due=10) -> dict:
    return await _ok(
        await api.post(
            f"{API}/credit-cards",
            json={
                "name": name,
                "credit_limit": 5000,
                "closing_day": closing,
                "due_day": due,
                "last_four_digits": last4,
            },
        ),
        201,
    )


async def _document(db_session, user) -> Document:
    doc = Document(
        user_id=user.id,
        file_path="/tmp/inexistente.pdf",
        file_hash="f" * 64,
        file_size=10,
        mime_type="application/pdf",
        original_filename="fatura.pdf",
        status=DocumentStatus.COMPLETED,
        document_type="fatura_cartao",
        extracted_data={"card_info": {"total_amount": 300.0}, "items": []},
    )
    db_session.add(doc)
    await db_session.commit()
    return doc


@pytest.mark.parametrize(
    "document_data,expected",
    [
        ({"card_last_digits": "4821"}, "Nubank Roxinho"),
        ({"card_issuer": "nubank"}, "Nubank Roxinho"),
        ({"card_issuer": "itau", "card_last_digits": "7310"}, "Itaú Click"),
    ],
)
async def test_identifica_o_cartao_pela_fatura(api, document_data, expected):
    await _card(api, "Nubank Roxinho", "4821")
    await _card(api, "Itaú Click", "7310", closing=25, due=5)

    result = await _ok(await api.post(f"{API}/invoices/detect-card", json=document_data))

    detected = {c["account_name"]: c["credit_card_id"] for c in result["detected_cards"]}
    assert expected in detected, result
    assert result["suggested_card_id"] == detected[expected]


async def test_cartao_desconhecido_nao_casa(api):
    await _card(api, "Nubank Roxinho", "4821")
    result = await _ok(
        await api.post(f"{API}/invoices/detect-card", json={"card_last_digits": "0000"})
    )
    assert result["detected_cards"] == []
    assert result["suggested_card_id"] is None


async def test_fatura_criada_do_documento(api, db_session, test_user):
    card = await _card(api, "Nubank Roxinho", "4821")
    doc = await _document(db_session, test_user)

    invoice = await _ok(
        await api.post(
            f"{API}/invoices/from-document",
            json={
                "document_id": doc.id,
                "credit_card_id": card["id"],
                "reference_month": 5,
                "reference_year": 2026,
                "total_amount": 300.0,
            },
        ),
        201,
    )

    assert (invoice["reference_month"], invoice["reference_year"]) == (5, 2026)
    again = await api.post(
        f"{API}/invoices/from-document",
        json={
            "document_id": doc.id,
            "credit_card_id": card["id"],
            "reference_month": 5,
            "reference_year": 2026,
        },
    )
    assert again.status_code in (400, 409)


async def _series_count(db_session, user_id) -> int:
    return await db_session.scalar(
        select(func.count())
        .select_from(InstallmentSeries)
        .where(InstallmentSeries.user_id == user_id)
    )


async def test_parcela_lida_da_fatura_seguinte_reaproveita_a_serie(api, db_session, test_user):
    """RN005: a parcela 2/10 que chega no PDF de junho não cria outra série nem duplica."""
    card = await _card(api, "Itaú Click", "7310", closing=25, due=5)
    first = await _ok(
        await api.post(
            f"{API}/transactions/confirm",
            json={
                "account_id": card["account_id"],
                "credit_card_id": card["id"],
                "amount": "420.00",
                "date": "2026-05-18",
                "description": "NOTEBOOK DELL 01/10",
                "is_installment": True,
                "installment_current": 1,
                "installment_total": 10,
                "create_future_installments": True,
            },
        ),
        201,
    )
    assert first["series_id"]
    assert await _series_count(db_session, test_user.id) == 1

    # o PDF de junho traz a parcela 2 com o nome um pouco diferente
    check = await _ok(
        await api.post(
            f"{API}/transactions/check-projected",
            json={
                "items": [{"index": 0, "description": "NOTEBOOK DELL 02/10", "amount": 420.0}],
                "credit_card_id": card["id"],
                "invoice_month": 6,
                "invoice_year": 2026,
            },
        )
    )
    assert check is not None

    second = await _ok(
        await api.post(
            f"{API}/transactions/confirm",
            json={
                "account_id": card["account_id"],
                "credit_card_id": card["id"],
                "amount": "420.00",
                "date": "2026-05-18",
                "description": "NOTEBOOK DELL 02/10",
                "is_installment": True,
                "installment_current": 2,
                "installment_total": 10,
                "invoice_month": 6,
                "invoice_year": 2026,
            },
        ),
        201,
    )

    assert await _series_count(db_session, test_user.id) == 1
    assert second["series_id"] == first["series_id"]
    parcel_2 = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.installment_series_id == first["series_id"],
            Transaction.installment_number == 2,
        )
    )
    assert parcel_2 == 1


async def test_parcela_do_meio_sem_historico_cria_a_serie(api, db_session, test_user):
    """Primeira fatura lida já está na parcela 4/6: a série nasce com o total certo."""
    card = await _card(api, "Nubank Roxinho", "4821")

    confirmed = await _ok(
        await api.post(
            f"{API}/transactions/confirm",
            json={
                "account_id": card["account_id"],
                "credit_card_id": card["id"],
                "amount": "99.90",
                "date": "2026-02-10",
                "description": "SAMSUNG 04/06",
                "is_installment": True,
                "installment_current": 4,
                "installment_total": 6,
                "invoice_month": 5,
                "invoice_year": 2026,
                "create_future_installments": True,
            },
        ),
        201,
    )

    series = await _ok(await api.get(f"{API}/installments/{confirmed['series_id']}"))
    assert series["installment_count"] == 6
    future = await db_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.installment_series_id == confirmed["series_id"],
            Transaction.installment_number > 4,
        )
    )
    assert future == 2


async def test_series_parecidas_sao_unidas(api, db_session, test_user):
    card = await _card(api, "Nubank Roxinho", "4821")
    ids = []
    for description in ("GELADEIRA BRASTEMP", "GELADEIRA BRASTEMP LTDA"):
        tx = await _ok(
            await api.post(
                f"{API}/transactions",
                json={
                    "description": description,
                    "amount": "250.00",
                    "date": date(2026, 5, 2).isoformat(),
                    "type": "expense",
                    "account_id": card["account_id"],
                    "credit_card_id": card["id"],
                    "is_installment": True,
                    "installment_current": 1,
                    "installment_total": 8,
                },
            ),
            201,
        )
        ids.append((await db_session.get(Transaction, tx["id"])).installment_series_id)

    groups = await _ok(await api.post(f"{API}/installments/detect-duplicates"))
    if len(set(ids)) == 2:
        merged = await _ok(
            await api.post(
                f"{API}/installments/merge",
                json={"source_series_id": ids[1], "target_series_id": ids[0]},
            )
        )
        assert merged["id"] == ids[0]
    assert groups is not None

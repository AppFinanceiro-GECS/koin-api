"""
#40 / RN005 e RN012: série de parcelas pelo serviço, nos caminhos que a leitura de
fatura usa (achar a série, conferir o que já foi lançado, marcar anteriores como pagas).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.account import Account, AccountType
from app.models.credit_card import CreditCard
from app.modules.installments.services.installment_service import InstallmentService


@pytest.fixture
async def card(db_session, test_user):
    account = Account(
        user_id=test_user.id, name="Nubank", type=AccountType.CREDIT_CARD.value, balance=0
    )
    db_session.add(account)
    await db_session.flush()
    credit_card = CreditCard(
        account_id=account.id,
        user_id=test_user.id,
        credit_limit=Decimal("5000"),
        closing_day=3,
        due_day=10,
    )
    db_session.add(credit_card)
    await db_session.flush()
    return credit_card


@pytest.fixture
async def series(db_session, test_user, card):
    service = InstallmentService(db_session)
    created = await service.create_series(
        user=test_user,
        description="Geladeira Brastemp",
        merchant_name="Brastemp",
        installment_amount=250.0,
        installment_count=6,
        first_installment_date=date(2026, 3, 2),
        account_id=card.account_id,
        credit_card_id=card.id,
    )
    await db_session.flush()
    return created


async def test_lancar_parcelas_e_status_da_serie(db_session, test_user, series, card):
    service = InstallmentService(db_session)
    for n, day in ((1, date(2026, 3, 2)), (2, date(2026, 4, 2))):
        await service.create_installment_transaction(
            user=test_user,
            series=series,
            installment_number=n,
            transaction_date=day,
            credit_card_id=card.id,
        )
    await db_session.flush()

    status = await service.get_series_status(series)

    assert status["series_id"] == series.id
    states = {i["number"]: i["status"] for i in status["installments"]}
    assert states[1] == states[2] == "paid"
    assert states[3] == "pending"
    assert len(states) == 6


async def test_parcela_repetida_e_recusada(db_session, test_user, series, card):
    service = InstallmentService(db_session)
    await service.create_installment_transaction(
        user=test_user,
        series=series,
        installment_number=1,
        transaction_date=date(2026, 3, 2),
        credit_card_id=card.id,
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.create_installment_transaction(
            user=test_user,
            series=series,
            installment_number=1,
            transaction_date=date(2026, 3, 2),
            credit_card_id=card.id,
        )

    assert exc.value.status_code == 409
    assert await service.find_existing_installment(series, 1) is not None


async def test_marcar_anteriores_como_pagas(db_session, test_user, series):
    """Quem começa a usar o app na parcela 4 tem as 3 anteriores criadas como pagas."""
    service = InstallmentService(db_session)

    created = await service.mark_previous_installments_as_paid(
        user=test_user, series=series, up_to_installment=4
    )
    await db_session.flush()

    assert sorted(t.installment_number for t in created) == [1, 2, 3]
    assert all(t.is_paid for t in created)
    assert series.paid_count == 3
    # rodar de novo não cria outra vez
    assert await service.mark_previous_installments_as_paid(test_user, series, 4) == []


async def test_acha_a_serie_por_estabelecimento_e_valor(db_session, test_user, series, card):
    service = InstallmentService(db_session)

    found = await service.find_matching_series(
        user=test_user,
        merchant_name="Brastemp",
        installment_amount=250.0,
        installment_total=6,
        account_id=card.account_id,
        transaction_date=date(2026, 5, 2),
        installment_number=3,
    )

    assert found is not None and found.id == series.id


async def test_duplicata_por_nome_parecido(db_session, test_user, series, card):
    service = InstallmentService(db_session)

    match = await service.find_potential_duplicate(
        user=test_user,
        merchant_name="BRASTEMP LTDA",
        installment_amount=251.0,
        installment_total=6,
        credit_card_id=card.id,
        min_similarity=0.5,
    )
    nothing = await service.find_potential_duplicate(
        user=test_user,
        merchant_name="Brastemp",
        installment_amount=900.0,
        installment_total=6,
        credit_card_id=card.id,
    )

    assert match is not None and match[0].id == series.id
    assert nothing is None


async def test_transacao_do_pdf_ja_lancada(db_session, test_user, series, card):
    service = InstallmentService(db_session)
    tx = await service.create_installment_transaction(
        user=test_user,
        series=series,
        installment_number=2,
        transaction_date=date(2026, 4, 2),
        is_paid=False,  # projetada: o PDF real ainda não chegou
        credit_card_id=card.id,
    )
    await db_session.flush()

    found = await service.find_matching_transaction_for_pdf(
        user=test_user,
        merchant_name="Brastemp",
        amount=250.0,
        transaction_date=date(2026, 4, 2),
        installment_number=2,
        installment_total=6,
        credit_card_id=card.id,
    )

    assert found is not None and found.id == tx.id


async def test_analisa_item_extraido(db_session, test_user, series, card):
    service = InstallmentService(db_session)

    known = await service.analyze_extracted_item(
        user=test_user,
        item={
            "description": "Brastemp",
            "amount": 250.0,
            "is_installment": True,
            "installment_current": 3,
            "installment_total": 6,
            "date": "2026-05-02",
        },
        account_id=card.account_id,
    )
    new = await service.analyze_extracted_item(
        user=test_user,
        item={
            "description": "Notebook Dell",
            "amount": 420.0,
            "is_installment": True,
            "installment_current": 1,
            "installment_total": 10,
        },
        account_id=card.account_id,
    )
    simple = await service.analyze_extracted_item(
        user=test_user,
        item={"description": "Padaria", "amount": 12.0},
        account_id=card.account_id,
    )

    assert known["is_installment"] and known["series_found"]["id"] == series.id
    assert new["series_found"] is None and new["suggestion"]
    assert simple["is_installment"] is False

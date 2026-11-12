"""
Comprovantes e o cartão: o pagamento da fatura sugere a fatura em aberto (pelo banco e pelo
valor) e a compra com o final do cartão vai para o cartão. Comprovante nunca cria cartão.
Dados fictícios: nenhum número real de cartão, fatura ou comprovante.
"""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.transaction import Transaction
from app.modules.credit_cards.services.card_matching import (
    MATCHED,
    NONE,
    UNREGISTERED,
    match_receipt_card,
)
from app.modules.credit_cards.services.invoice_payment_matching import (
    PAYMENT_AMBIGUOUS,
    PAYMENT_MATCHED,
    PAYMENT_NONE,
    match_invoice_payment,
)
from app.modules.documents.services.extraction_validator import ExtractionValidator
from app.modules.documents.services.response_parser import ResponseParser


@pytest_asyncio.fixture
async def auth(client, test_user, db_session):
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"
    return client


async def _card(db, user, name, digits=None, bank_id=None, closing=5, due=12):
    account = Account(user_id=user.id, name=name, type="credit_card", balance=0)
    db.add(account)
    await db.flush()
    card = CreditCard(
        user_id=user.id,
        account_id=account.id,
        nickname=name,
        last_four_digits=digits,
        bank_id=bank_id,
        closing_day=closing,
        due_day=due,
        credit_limit=1000,
    )
    db.add(card)
    await db.flush()
    return card


async def _invoice(db, user, card, total, month=11, status=InvoiceStatus.CLOSED, paid="0"):
    invoice = CreditCardInvoice(
        user_id=user.id,
        credit_card_id=card.id,
        reference_month=month,
        reference_year=2026,
        closing_date=date(2026, month, card.closing_day),
        due_date=date(2026, month, card.due_day),
        total_amount=Decimal(total),
        paid_amount=Decimal(paid),
        status=status.value,
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def _checking(db, user):
    account = Account(user_id=user.id, name="Conta corrente", type="checking", balance=0)
    db.add(account)
    await db.flush()
    return account


async def _receipt(db, user, doc_type, amount, payment_card=None, n="1", when="2026-11-10"):
    data = {
        "items": [{"description": "Recebedor fictício", "amount": amount, "date": when}],
        "total_amount": amount,
        "document_type": doc_type,
    }
    if payment_card:
        data["payment_card"] = payment_card
    doc = Document(
        user_id=user.id,
        file_path=f"/tmp/comprovante-{n}.jpg",
        file_hash=(n.encode().hex() + "f" * 64)[:64],
        file_size=10,
        mime_type="image/jpeg",
        original_filename=f"comprovante-{n}.jpg",
        status=DocumentStatus.COMPLETED.value,
        document_type=doc_type,
        extracted_data=data,
    )
    db.add(doc)
    await db.flush()
    return doc


PAGOU_NUBANK = {"card_issuer": "nubank", "card_bank": "Nubank"}
FATURA_PAGA = DocumentType.COMPROVANTE_FATURA.value
COMPRA = DocumentType.COMPROVANTE.value


# ---------------------------------------------------------------- leitura do documento


def test_tipo_comprovante_de_pagamento_de_fatura():
    assert DocumentType.from_string("comprovante_fatura") == DocumentType.COMPROVANTE_FATURA
    assert (
        DocumentType.from_string("comprovante_pagamento_fatura") == DocumentType.COMPROVANTE_FATURA
    )
    assert DocumentType.from_string("pagamento de fatura") == DocumentType.COMPROVANTE_FATURA
    # a fatura em si continua sendo fatura
    assert DocumentType.from_string("fatura_cartao") == DocumentType.FATURA_CARTAO
    assert DocumentType.from_string("fatura") == DocumentType.FATURA_CARTAO


def test_leitura_guarda_o_cartao_do_comprovante():
    parsed = ResponseParser().parse(
        '{"document_type": "comprovante", "total_amount": 59.9,'
        ' "payment_card": {"card_brand": "VISA", "card_last_digits": "**** **** **** 4321"},'
        ' "items": [{"description": "Padaria Fictícia", "amount": 59.9, "date": "2026-11-10"}]}'
    )

    assert parsed["payment_card"] == {
        "card_issuer": None,
        "card_bank": None,
        "card_brand": "visa",
        "card_last_digits": "4321",
    }


def test_validador_mantem_o_pagamento_da_fatura():
    items = [
        {
            "description": "Pagamento fatura Nubank",
            "amount": 321.0,
            "transaction_type": "pagamento",
            "date": "2026-11-10",
        }
    ]

    cleaned = ExtractionValidator().validate_and_clean(items, None, FATURA_PAGA, 321.0)

    assert [(i["description"], i["amount"]) for i in cleaned] == [
        ("Pagamento fatura Nubank", 321.0)
    ]


# ------------------------------------------- 1. comprovante de pagamento -> fatura paga


async def test_pagamento_sugere_fatura_do_cartao_pelo_banco_e_valor(db_session, test_user):
    nubank = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank")
    inter = await _card(db_session, test_user, "Inter", digits="1111", bank_id="inter")
    fatura = await _invoice(db_session, test_user, nubank, "321.00")
    await _invoice(db_session, test_user, inter, "321.00")  # mesmo valor, outro banco

    match = await match_invoice_payment(
        db_session, test_user, {"total_amount": 321.0, "payment_card": PAGOU_NUBANK}
    )

    assert match.status == PAYMENT_MATCHED
    assert match.invoice.invoice_id == fatura.id
    assert match.invoice.credit_card_name == "Roxinho final 9876"
    assert match.amount_matches is True


async def test_pagamento_parcial_sugere_a_fatura_que_vence_mais_perto(db_session, test_user):
    nubank = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank")
    await _invoice(db_session, test_user, nubank, "200.00", month=10, status=InvoiceStatus.OPEN)
    novembro = await _invoice(db_session, test_user, nubank, "321.00", month=11)

    match = await match_invoice_payment(
        db_session,
        test_user,
        {
            "total_amount": 100.0,
            "payment_card": PAGOU_NUBANK,
            "items": [{"amount": 100.0, "date": "2026-11-11"}],
        },
    )

    assert match.status == PAYMENT_MATCHED
    assert match.invoice.invoice_id == novembro.id
    assert match.amount_matches is False
    assert len(match.candidates) == 2


async def test_pagamento_sem_banco_casa_pelo_valor(db_session, test_user):
    nubank = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank")
    inter = await _card(db_session, test_user, "Inter", digits="1111", bank_id="inter")
    await _invoice(db_session, test_user, nubank, "321.00")
    fatura_inter = await _invoice(db_session, test_user, inter, "87.45")

    match = await match_invoice_payment(db_session, test_user, {"total_amount": 87.45})
    assert match.status == PAYMENT_MATCHED
    assert match.invoice.invoice_id == fatura_inter.id

    # valor que não fecha com nenhuma: a pessoa escolhe entre as faturas em aberto
    other = await match_invoice_payment(db_session, test_user, {"total_amount": 50.0})
    assert other.status == PAYMENT_AMBIGUOUS
    assert len(other.candidates) == 2


async def test_pagamento_de_banco_sem_cartao_nao_sugere_outra_fatura(db_session, test_user):
    inter = await _card(db_session, test_user, "Inter", digits="1111", bank_id="inter")
    await _invoice(db_session, test_user, inter, "321.00")

    match = await match_invoice_payment(
        db_session, test_user, {"total_amount": 321.0, "payment_card": PAGOU_NUBANK}
    )

    assert match.status == PAYMENT_NONE
    assert match.invoice is None


async def test_comprovante_de_pagamento_marca_a_fatura_como_paga(auth, db_session, test_user):
    nubank = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank")
    fatura = await _invoice(db_session, test_user, nubank, "321.00")
    conta = await _checking(db_session, test_user)
    doc = await _receipt(db_session, test_user, FATURA_PAGA, 321.0, PAGOU_NUBANK)
    await db_session.commit()

    body = (await auth.get(f"/api/v1/documents/{doc.id}")).json()

    assert body["document_type"] == "comprovante_fatura"
    # o pagamento não é despesa do cartão nem sugere cadastrar cartão
    assert body["card_match"]["status"] == "none"
    payment = body["invoice_payment"]
    assert payment["status"] == "matched"
    assert payment["invoice"]["invoice_id"] == fatura.id
    assert payment["amount_paid"] == 321.0
    assert payment["payment_date"] == "2026-11-10"

    # o app paga com a conta de origem escolhida pela pessoa
    paid = await auth.post(
        f"/api/v1/invoices/{fatura.id}/pay",
        json={
            "amount": payment["amount_paid"],
            "payment_account_id": conta.id,
            "payment_date": payment["payment_date"],
        },
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"

    # mandar o mesmo comprovante de novo não sugere pagar outra vez
    again = (await auth.get(f"/api/v1/documents/{doc.id}")).json()["invoice_payment"]
    assert again["status"] == "already_paid"
    assert again["invoice"]["invoice_id"] == fatura.id


# --------------------------------------- 2. comprovante de compra com final -> cartão


async def test_compra_com_final_reconhece_o_cartao(db_session, test_user):
    card = await _card(db_session, test_user, "Visa da Casa", digits="4321")

    match = await match_receipt_card(
        db_session, test_user, {"card_last_digits": "4321", "card_brand": "visa"}, COMPRA
    )

    assert match.status == MATCHED
    assert match.credit_card_id == card.id


async def test_compra_sem_final_fica_na_conta_comum(db_session, test_user):
    await _card(db_session, test_user, "Visa da Casa", digits="4321")

    match = await match_receipt_card(db_session, test_user, {"card_brand": "visa"}, COMPRA)

    assert match.status == NONE


async def test_compra_com_final_desconhecido_sugere_cadastrar(auth, db_session, test_user):
    doc = await _receipt(
        db_session,
        test_user,
        COMPRA,
        59.9,
        {"card_last_digits": "4321", "card_brand": "visa"},
    )
    await db_session.commit()

    body = (await auth.get(f"/api/v1/documents/{doc.id}")).json()

    assert body["payment_card"]["card_last_digits"] == "4321"
    match = body["card_match"]
    assert match["status"] == UNREGISTERED
    assert match["suggestion"]["last_four_digits"] == "4321"
    assert match["suggestion"]["card_brand"] == "Visa"
    assert match["suggestion"]["name"] == "Visa"
    # comprovante nunca cria cartão sozinho
    response = await auth.post(f"/api/v1/credit-cards/from-document/{doc.id}")
    assert response.status_code == 422
    assert await db_session.scalar(select(func.count(CreditCard.id))) == 0


async def test_compra_com_final_entra_na_fatura_do_cartao(auth, db_session, test_user):
    card = await _card(db_session, test_user, "Visa da Casa", digits="4321", closing=5)
    doc = await _receipt(
        db_session, test_user, COMPRA, 59.9, {"card_last_digits": "4321"}, when="2026-11-10"
    )
    await db_session.commit()

    match = (await auth.get(f"/api/v1/documents/{doc.id}")).json()["card_match"]
    assert match == {
        "status": "matched",
        "credit_card_id": card.id,
        "credit_card_name": "Visa da Casa final 4321",
        "candidate_ids": [],
        "suggestion": None,
    }

    # o app confirma na conta do cartão com credit_card_id; a API acha a fatura pela data
    response = await auth.post(
        "/api/v1/transactions/batch-confirm",
        json={
            "items": [
                {
                    "document_id": doc.id,
                    "account_id": card.account_id,
                    "credit_card_id": card.id,
                    "payment_method": "credit_card",
                    "amount": 59.9,
                    "date": "2026-11-10",
                    "description": "Padaria Fictícia",
                }
            ]
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["success_count"] == 1

    tx = await db_session.scalar(select(Transaction).where(Transaction.document_id == doc.id))
    assert tx.credit_card_id == card.id
    assert tx.account_id == card.account_id
    invoice = await db_session.get(CreditCardInvoice, tx.invoice_id)
    # fecha dia 5: compra do dia 10/11 cai na fatura de dezembro
    assert (invoice.reference_month, invoice.reference_year) == (12, 2026)

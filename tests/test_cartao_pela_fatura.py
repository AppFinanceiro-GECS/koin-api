"""
O cartão nasce da fatura: reconhecimento pelo final e pelo banco, cadastro a partir da
fatura lida e projeção das parcelas já compradas nos próximos meses.
Dados fictícios: nenhum número real de cartão ou fatura.
"""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.installment import InstallmentSeries
from app.modules.credit_cards.services.card_matching import (
    AMBIGUOUS,
    MATCHED,
    NEW,
    NONE,
    match_card,
)
from app.modules.credit_cards.services.outlook_service import build_outlook

FATURA = {
    "card_issuer": "nubank",
    "card_bank": "Nu Pagamentos",
    "card_brand": "mastercard",
    "card_last_digits": "9876",
    "card_name": "Nubank Ultravioleta",
    "invoice_month": 11,
    "invoice_year": 2026,
    "closing_date": "2026-11-05",
    "due_date": "2026-11-12",
    "total_amount": 321.0,
    "credit_limit": 5000.0,
}


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


async def _document(db, user, card_info, doc_type=DocumentType.FATURA_CARTAO.value, n="1"):
    doc = Document(
        user_id=user.id,
        file_path=f"/tmp/fatura-{n}.pdf",
        file_hash=(n.encode().hex() + "0" * 64)[:64],
        file_size=10,
        mime_type="application/pdf",
        original_filename=f"fatura-{n}.pdf",
        status=DocumentStatus.COMPLETED.value,
        document_type=doc_type,
        extracted_data={"items": [], "card_info": card_info},
    )
    db.add(doc)
    await db.flush()
    return doc


async def test_reconhece_cartao_pelo_final(db_session, test_user):
    card = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank")
    await _card(db_session, test_user, "Outro", digits="1111")

    match = await match_card(db_session, test_user, FATURA, "fatura_cartao")

    assert match.status == MATCHED
    assert match.credit_card_id == card.id
    assert match.credit_card_name == "Roxinho final 9876"


async def test_mesmo_final_em_bancos_diferentes_desempata_pelo_banco(db_session, test_user):
    await _card(db_session, test_user, "Inter", digits="9876", bank_id="inter")
    nubank = await _card(db_session, test_user, "Nubank", digits="9876", bank_id="nubank")

    match = await match_card(db_session, test_user, FATURA, "fatura_cartao")

    assert match.status == MATCHED
    assert match.credit_card_id == nubank.id


async def test_mesmo_final_sem_como_desempatar_pede_para_escolher(db_session, test_user):
    a = await _card(db_session, test_user, "Cartão A", digits="9876")
    b = await _card(db_session, test_user, "Cartão B", digits="9876")

    match = await match_card(db_session, test_user, FATURA, "fatura_cartao")

    assert match.status == AMBIGUOUS
    assert set(match.candidate_ids) == {a.id, b.id}


async def test_cartao_cadastrado_sem_final_bate_pelo_banco(db_session, test_user):
    card = await _card(db_session, test_user, "Nubank", bank_id="nubank")

    match = await match_card(db_session, test_user, FATURA, "fatura_cartao")

    assert match.status == MATCHED
    assert match.credit_card_id == card.id


async def test_fatura_de_cartao_novo_traz_sugestao(db_session, test_user):
    match = await match_card(db_session, test_user, FATURA, "fatura_cartao")

    assert match.status == NEW
    s = match.suggestion
    assert s.name == "Nubank Ultravioleta"
    assert s.last_four_digits == "9876"
    assert s.bank_id == "nubank"
    assert s.card_brand == "Mastercard"
    assert (s.closing_day, s.due_day) == (5, 12)
    assert s.credit_limit == 5000.0


async def test_comprovante_nao_sugere_cartao(db_session, test_user):
    comprovante = {"card_last_digits": "4321", "card_brand": "visa"}

    match = await match_card(db_session, test_user, comprovante, "comprovante")

    assert match.status == NONE
    assert match.suggestion is None


async def test_documento_lido_informa_o_cartao(auth, db_session, test_user):
    card = await _card(db_session, test_user, "Roxinho", digits="9876")
    doc = await _document(db_session, test_user, FATURA)
    await db_session.commit()

    body = (await auth.get(f"/api/v1/documents/{doc.id}")).json()

    assert body["card_match"]["status"] == "matched"
    assert body["card_match"]["credit_card_id"] == card.id


async def test_cadastrar_cartao_pela_fatura_nao_duplica(auth, db_session, test_user):
    doc = await _document(db_session, test_user, FATURA)
    await db_session.commit()

    first = await auth.post(f"/api/v1/credit-cards/from-document/{doc.id}")
    second = await auth.post(f"/api/v1/credit-cards/from-document/{doc.id}")

    assert first.status_code == 201, first.text
    created = first.json()
    assert created["account_name"] == "Nubank Ultravioleta"
    assert created["last_four_digits"] == "9876"
    assert (created["closing_day"], created["due_day"]) == (5, 12)
    assert created["credit_limit"] == 5000.0
    assert created["account_color"] == "#820AD1"
    assert second.status_code == 200
    assert second.json()["id"] == created["id"]
    assert await db_session.scalar(select(func.count(CreditCard.id))) == 1


async def test_comprovante_nao_cadastra_cartao(auth, db_session, test_user):
    doc = await _document(
        db_session, test_user, {"card_last_digits": "4321"}, DocumentType.COMPROVANTE.value
    )
    await db_session.commit()

    response = await auth.post(f"/api/v1/credit-cards/from-document/{doc.id}")

    assert response.status_code == 422
    assert response.json()["code"] == "not_an_invoice"


async def test_projecao_soma_parcelas_no_mes_da_fatura(db_session, test_user):
    # fecha dia 5: parcela do dia 10 cai na fatura do mês seguinte
    card = await _card(db_session, test_user, "Roxinho", digits="9876", closing=5)
    db_session.add(
        InstallmentSeries(
            user_id=test_user.id,
            description="Geladeira",
            merchant_name="Loja",
            total_amount=Decimal("300"),
            installment_amount=Decimal("100"),
            installment_count=3,
            first_installment_date=date(2026, 10, 10),
            account_id=card.account_id,
            credit_card_id=card.id,
        )
    )
    await db_session.flush()

    outlook = await build_outlook(db_session, test_user, 4, "me", date(2026, 11, 20))

    by_month = {(m.year, m.month): m.total for m in outlook.months}
    # parcelas em 10/10, 10/11 e 10/12 -> faturas de nov, dez e jan; nov é o mês atual
    assert by_month == {(2026, 11): 100.0, (2026, 12): 100.0, (2027, 1): 100.0, (2027, 2): 0.0}
    assert outlook.total == 300.0


async def test_projecao_separa_por_cartao(db_session, test_user):
    roxo = await _card(db_session, test_user, "Roxinho", digits="9876", bank_id="nubank", closing=5)
    laranja = await _card(
        db_session, test_user, "Laranjinha", digits="1234", bank_id="inter", closing=25
    )
    for card, desc, valor, n in ((roxo, "Geladeira", "100", 3), (laranja, "Fone", "40", 2)):
        db_session.add(
            InstallmentSeries(
                user_id=test_user.id,
                description=desc,
                merchant_name="Loja",
                total_amount=Decimal(valor) * n,
                installment_amount=Decimal(valor),
                installment_count=n,
                first_installment_date=date(2026, 11, 10),
                account_id=card.account_id,
                credit_card_id=card.id,
            )
        )
    await db_session.flush()

    outlook = await build_outlook(db_session, test_user, 3, "me", date(2026, 11, 1))

    # o cartão que mais pesa vem primeiro
    assert [(c.credit_card_id, c.bank_id, c.total) for c in outlook.cards] == [
        (roxo.id, "nubank", 200.0),  # a 3ª parcela cai em fevereiro, fora da janela
        (laranja.id, "inter", 80.0),
    ]
    # Roxinho fecha dia 5: dia 10 cai na fatura de dezembro. Laranjinha fecha dia 25: novembro
    nov, dez, jan = outlook.months
    assert [(b.credit_card_id, b.total) for b in nov.by_card] == [(laranja.id, 40.0)]
    assert [(b.credit_card_id, b.total) for b in dez.by_card] == [
        (roxo.id, 100.0),
        (laranja.id, 40.0),
    ]
    assert dez.total == sum(b.total for b in dez.by_card)
    item = dez.by_card[0].items[0]
    assert (item.description, item.installment_number, item.installment_count) == (
        "Geladeira",
        1,
        3,
    )
    assert [(b.credit_card_id, b.total) for b in jan.by_card] == [(roxo.id, 100.0)]


async def test_projecao_pela_rota(auth):
    response = await auth.get("/api/v1/invoices/outlook", params={"months": 3})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "me"
    assert len(body["months"]) == 3
    assert body["total"] == 0

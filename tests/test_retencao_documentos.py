"""
#50: retenção das faturas enviadas. Apaga o original e os dados extraídos só do que
foi confirmado (ou falhou) há mais do prazo; nunca o que ainda pode ser confirmado.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.utils import utc_now
from app.models.account import Account, AccountType
from app.models.document import Document, DocumentStatus
from app.models.transaction import Transaction, TransactionType
from app.modules.documents.services.retention import purge_expired_documents

OLD = timedelta(days=31)


@pytest.fixture
async def account(db_session, test_user):
    acc = Account(user_id=test_user.id, name="Banco", type=AccountType.BANK.value, balance=0)
    db_session.add(acc)
    await db_session.flush()
    return acc


async def _document(db_session, user, tmp_path, name, status, age=OLD, path=None):
    file_path = path or tmp_path / f"{name}.pdf"
    if path is None:
        file_path.write_bytes(b"%PDF fatura")
    doc = Document(
        user_id=user.id,
        file_path=str(file_path),
        file_hash=name.ljust(64, "0"),
        file_size=11,
        mime_type="application/pdf",
        original_filename=f"{name}.pdf",
        status=status,
        created_at=utc_now() - age,
        processed_at=utc_now() - age,
        extracted_data={"items": [{"description": "Mercado", "amount": 10}]},
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


async def _confirm(db_session, user, account, doc):
    db_session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            description="Mercado",
            amount=Decimal("10"),
            date=date.today(),
            type=TransactionType.EXPENSE,
            document_id=doc.id,
        )
    )
    await db_session.flush()


async def test_confirmada_ha_mais_do_prazo_perde_arquivo_e_dados(
    db_session, test_user, account, tmp_path
):
    doc = await _document(db_session, test_user, tmp_path, "confirmada", DocumentStatus.COMPLETED)
    await _confirm(db_session, test_user, account, doc)

    assert await purge_expired_documents(db_session, days=30) == 1

    await db_session.refresh(doc)
    assert not (tmp_path / "confirmada.pdf").exists()
    assert doc.extracted_data is None
    assert doc.file_purged_at is not None
    # a linha fica: hash para reenvio e vínculo com a transação
    assert doc.file_hash


async def test_falha_antiga_perde_o_arquivo(db_session, test_user, tmp_path):
    await _document(db_session, test_user, tmp_path, "falhou", DocumentStatus.FAILED)
    assert await purge_expired_documents(db_session, days=30) == 1
    assert not (tmp_path / "falhou.pdf").exists()


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.COMPLETED,  # lida, mas ainda não confirmada
        DocumentStatus.WAITING_AI,
        DocumentStatus.PROCESSING,
        DocumentStatus.PENDING,
    ],
)
async def test_nao_apaga_o_que_ainda_pode_ser_confirmado(db_session, test_user, tmp_path, status):
    doc = await _document(db_session, test_user, tmp_path, f"aberta-{status.value}", status)

    assert await purge_expired_documents(db_session, days=30) == 0
    await db_session.refresh(doc)
    assert (tmp_path / f"aberta-{status.value}.pdf").exists()
    assert doc.extracted_data is not None


async def test_dentro_do_prazo_fica(db_session, test_user, account, tmp_path):
    doc = await _document(
        db_session, test_user, tmp_path, "recente", DocumentStatus.COMPLETED, age=timedelta(days=5)
    )
    await _confirm(db_session, test_user, account, doc)

    assert await purge_expired_documents(db_session, days=30) == 0
    assert (tmp_path / "recente.pdf").exists()


async def test_arquivo_dividido_so_sai_quando_ninguem_mais_usa(
    db_session, test_user, account, tmp_path
):
    shared = tmp_path / "compartilhado.pdf"
    shared.write_bytes(b"%PDF")
    expired = await _document(
        db_session, test_user, tmp_path, "velho", DocumentStatus.COMPLETED, path=shared
    )
    await _confirm(db_session, test_user, account, expired)
    await _document(
        db_session,
        test_user,
        tmp_path,
        "novo",
        DocumentStatus.PENDING,
        age=timedelta(0),
        path=shared,
    )

    assert await purge_expired_documents(db_session, days=30) == 1
    assert shared.exists()


async def test_zero_desliga(db_session, test_user, tmp_path):
    await _document(db_session, test_user, tmp_path, "falhou", DocumentStatus.FAILED)
    assert await purge_expired_documents(db_session, days=0) == 0


async def test_rodar_de_novo_nao_repete(db_session, test_user, tmp_path):
    await _document(db_session, test_user, tmp_path, "falhou", DocumentStatus.FAILED)
    assert await purge_expired_documents(db_session, days=30) == 1
    assert await purge_expired_documents(db_session, days=30) == 0


def test_job_agendado_no_modulo_de_documentos():
    from app.core.scheduler import JOBS

    assert any(
        job_id == "purge_expired_documents" and module == "documents" for module, *_, job_id in JOBS
    )

"""
Envio e leitura de faturas (insumos de 11/11):
- PDF com bytes nulos antes do `%PDF` (fatura do Inter) era recusado com 415.
- Tela de checkout de ingressos (total R$ 0,00) virava "fatura" com 6 itens: agora a IA
  classifica como nao_financeiro e o app pede lançamento manual.
IA sempre simulada.
"""

import io
from pathlib import Path

import pymupdf
import pytest
from fastapi import BackgroundTasks, UploadFile
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.modules.documents.services import ai_failures
from app.modules.documents.services import document_service as svc
from app.modules.documents.services.ai_failures import (
    NO_ITEMS_FOUND,
    NOT_FINANCIAL_DOCUMENT,
    classify,
)
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.llm_ocr_service import LLMOCRService
from app.modules.documents.services.response_parser import ResponseParser
from app.modules.documents.services.upload_files import clean_filename, detect_type, pdf_start


def _pdf(text: str = "Fatura Inter") -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


# ---------- upload ----------


def test_pdf_com_zeros_antes_do_cabecalho_e_pdf():
    content = b"\x00" * 300_000 + _pdf()
    assert detect_type(content, "fatura-inter.pdf", images_only=False) == (
        "pdf",
        "application/pdf",
    )
    assert pdf_start(content) == 300_000


def test_pdf_com_lixo_no_primeiro_kb_e_aceito_mas_lixo_grande_nao():
    assert pdf_start(b"lixo\r\n" + _pdf()) == 6
    assert pdf_start(b"MZ" + b"x" * 5000 + b"%PDF-1.7") is None
    assert pdf_start(_pdf()) is None  # cabeçalho no byte 0: caminho normal


def test_nome_do_arquivo_fica_legivel():
    assert (
        clean_filename("Captura%20de%20Tela%202024-06-02%20a%CC%80(s)%2011.28.11.pdf")
        == "Captura de Tela 2024-06-02 à(s) 11.28.11.pdf"
    )
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename(None) == "arquivo"


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(svc, "process_document_background", _noop)
    return tmp_path


@pytest.mark.asyncio
async def test_upload_da_fatura_inter_guarda_o_pdf_sem_os_zeros(
    client: AsyncClient, test_user: User, db_session: AsyncSession, upload_dir
):
    app.dependency_overrides[get_current_user] = lambda: test_user
    pdf = _pdf()
    response = await client.post(
        "/api/v1/documents/async",
        files={"file": ("fatura-inter-2026-10.pdf", b"\x00" * 2048 + pdf, "application/pdf")},
    )

    assert response.status_code == 202, response.text
    document = await db_session.get(Document, response.json()["id"])
    assert document.mime_type == "application/pdf"
    assert Path(document.file_path).read_bytes() == pdf


# ---------- leitura ----------


def test_parser_recusa_documento_nao_financeiro():
    result = ResponseParser().parse(
        '{"document_type": "nao_financeiro", "rejection_reason": "tela de checkout", "items": []}'
    )
    assert result["error"] == "not_financial_document"
    assert result["rejection_reason"] == "tela de checkout"
    assert result["items"] == []


def test_codigo_do_catalogo_vira_a_falha_certa():
    assert classify("not_financial_document") is NOT_FINANCIAL_DOCUMENT
    assert classify("no_items_found") is NO_ITEMS_FOUND
    assert NOT_FINANCIAL_DOCUMENT.retry_after is None  # não é falha da IA: não reprocessa


@pytest.mark.asyncio
async def test_leitura_sem_itens_pede_lancamento_manual(monkeypatch):
    class Provider:
        async def extract_from_image(self, content, mime):
            return {"items": [], "document_type": "cupom_fiscal"}

    service = LLMOCRService(provider="google", model="x")
    monkeypatch.setattr(service, "_get_provider", lambda prompt=None: Provider())
    result = await service.extract_from_image(b"img", "image/jpeg")
    assert result["error"] == "no_items_found"


@pytest.fixture
def background_db(monkeypatch, tmp_path, test_engine):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(
        svc,
        "async_session_maker",
        async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False),
    )
    circuit = ai_failures.AICircuit()
    monkeypatch.setattr(svc, "ai_circuit", circuit)
    return circuit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ai_result,failure",
    [
        (
            {"items": [], "document_type": "nao_financeiro", "error": "not_financial_document"},
            NOT_FINANCIAL_DOCUMENT,
        ),
        (
            {"items": [], "document_type": "fatura_cartao", "error": "no_items_found"},
            NO_ITEMS_FOUND,
        ),
    ],
)
async def test_checkout_de_ingresso_falha_com_mensagem_e_sem_retentativa(
    db_session, monkeypatch, background_db, ai_result, failure
):
    async def extract(self, *args, **kwargs):
        return ai_result

    monkeypatch.setattr(LLMOCRService, "extract_from_image", extract)
    user = User(email="checkout@example.com", name="Checkout", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    tasks = BackgroundTasks()
    file = UploadFile(file=io.BytesIO(_pdf("AVANCAR R$ 0,00")), filename="Captura.pdf")
    response = await DocumentService(db_session).upload_async(user, file, tasks)
    for task in tasks.tasks:
        await task.func(*task.args, **task.kwargs)
    document = await db_session.get(Document, response.id)
    await db_session.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.error_code == failure.code
    assert document.error_message == failure.message
    assert document.next_retry_at is None
    assert not background_db.is_open()


# ---------- validador (fatura do Inter) ----------


def _item(description, amount, date="2026-10-24", kind="compra"):
    return {"description": description, "amount": amount, "date": date, "transaction_type": kind}


def test_nome_terminado_em_sa_nao_e_cabecalho_de_secao():
    from app.modules.documents.services.extraction_validator import ExtractionValidator

    items = [_item("FULANO DE SOUSA", 8.0), _item("BELTRANO DA COSTA", 8.0, "2026-10-28")]
    kept = ExtractionValidator().remove_section_headers(items, {"total_amount": 16.0})
    assert len(kept) == 2
    # o cabeçalho real (empresa com sufixo separado e sem data) continua saindo
    header = {"description": "KAS S C T LTDA", "amount": 679.49, "date": None}
    assert ExtractionValidator().remove_section_headers([header], None) == []


def test_pagamentos_da_fatura_anterior_saem_quando_a_soma_fecha():
    from app.modules.documents.services.extraction_validator import ExtractionValidator

    items = [
        _item("DEB AUT PARCIAL", -1200.00, "2026-10-07", "pagamento"),
        _item("PAGAMENTO ON LINE", -800.00, "2026-10-08", "pagamento"),
        _item("IOF", 5.88, "2026-10-31", "encargo"),
        _item("SUPERMERCADO", 94.12),
    ]
    out = ExtractionValidator().validate_and_clean(
        items, {"total_amount": 100.0, "card_issuer": "inter"}, "fatura_cartao"
    )
    assert [i["description"] for i in out] == ["IOF", "SUPERMERCADO"]
    assert round(sum(i["amount"] for i in out), 2) == 100.0


@pytest.mark.asyncio
async def test_reenvio_de_documento_que_falhou_reprocessa_sem_409(
    client: AsyncClient, test_user: User, db_session: AsyncSession, upload_dir
):
    app.dependency_overrides[get_current_user] = lambda: test_user
    pdf = _pdf("Checkout")
    files = {"file": ("captura.pdf", pdf, "application/pdf")}
    first = await client.post("/api/v1/documents/async", files=files)
    assert first.status_code == 202
    document = await db_session.get(Document, first.json()["id"])
    document.status = DocumentStatus.FAILED
    await db_session.commit()

    again = await client.post("/api/v1/documents/async", files=files)
    assert again.status_code == 202, again.text
    assert again.json()["id"] == document.id

    # documento concluído continua avisando que já foi recebido
    await db_session.refresh(document)
    document.status = DocumentStatus.COMPLETED
    await db_session.commit()
    third = await client.post("/api/v1/documents/async", files=files)
    assert third.status_code == 409

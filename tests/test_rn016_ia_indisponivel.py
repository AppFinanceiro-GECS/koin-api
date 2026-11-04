"""
RN016 (#57) e processamento resiliente (#37): falha da IA não perde o envio, a mensagem
é do catálogo e o scheduler conclui o documento sozinho. IA sempre simulada.
"""

import asyncio
import io
from datetime import timedelta

import pytest
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.core.utils import utc_now
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.modules.documents.services import ai_failures
from app.modules.documents.services import document_service as svc
from app.modules.documents.services.ai_failures import (
    AI_BUSY,
    AI_QUOTA_EXHAUSTED,
    AI_UNAVAILABLE,
    UNREADABLE_DOCUMENT,
    classify,
)
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.llm_ocr_service import LLMOCRService

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
OK = {"items": [{"description": "Mercado", "amount": 10.0}], "document_type": "cupom_fiscal"}
RAW_429 = "429 RESOURCE_EXHAUSTED. {'error': {'message': 'Quota exceeded for metric generate_content_free_tier_requests'}}"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path, test_engine):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mistral_api_key", None)
    # a tarefa de fundo e o job abrem sessão própria: mesmo banco em memória dos testes
    monkeypatch.setattr(
        svc,
        "async_session_maker",
        async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False),
    )
    circuit = ai_failures.AICircuit()
    monkeypatch.setattr(svc, "ai_circuit", circuit)
    monkeypatch.setattr(ai_failures, "ai_circuit", circuit)
    return circuit


def fake_ai(monkeypatch, *outcomes):
    """Cada chamada consome um resultado: dict devolvido ou exceção levantada."""
    calls = []
    queue = list(outcomes)

    async def extract(self, *args, **kwargs):
        calls.append(1)
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(LLMOCRService, "extract_from_image", extract)
    return calls


async def _user(db_session) -> User:
    user = User(email="rn016@example.com", name="RN016", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    return user


async def _upload_async(db_session, user, content=PNG, name="fatura.png"):
    tasks = BackgroundTasks()
    file = UploadFile(file=io.BytesIO(content), filename=name)
    response = await DocumentService(db_session).upload_async(user, file, tasks)
    for task in tasks.tasks:
        await task.func(*task.args, **task.kwargs)
    document = await db_session.get(Document, response.id)
    await db_session.refresh(document)
    return response, document


async def test_cota_esgotada_guarda_e_o_job_conclui_sozinho(db_session, monkeypatch, isolated):
    """Critério de aceite da RN016."""
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": RAW_429}, OK)

    response, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.WAITING_AI
    assert document.error_code == "ai_quota_exhausted"
    assert document.error_message == AI_QUOTA_EXHAUSTED.message
    assert document.next_retry_at > utc_now()
    assert isolated.state() == "quota_exhausted"

    # o limite renova: pausa e próxima tentativa vencidas
    isolated.paused_until = utc_now() - timedelta(seconds=1)
    document.next_retry_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    assert await svc.retry_waiting_documents() == 1
    await db_session.refresh(document)
    assert document.status == DocumentStatus.COMPLETED
    assert document.error_code is None and document.error_message is None
    assert isolated.state() == "ok"


async def test_com_disjuntor_aberto_nao_chama_a_ia(db_session, monkeypatch, isolated):
    user = await _user(db_session)
    calls = fake_ai(monkeypatch)
    isolated.paused_until = utc_now() + timedelta(minutes=30)

    _, document = await _upload_async(db_session, user)

    assert calls == []
    assert document.status == DocumentStatus.WAITING_AI
    assert document.next_retry_at == isolated.paused_until
    assert await svc.retry_waiting_documents() == 0


async def test_sobrecarga_vai_para_a_fila_sem_abrir_o_disjuntor(db_session, monkeypatch, isolated):
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": "503 UNAVAILABLE. high demand"})

    _, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.WAITING_AI
    assert document.error_code == "ai_busy"
    assert not isolated.is_open()
    assert isolated.state() == "degraded"


async def test_chave_ausente_nao_expoe_nome_de_variavel(db_session, monkeypatch, client):
    user = await _user(db_session)
    fake_ai(monkeypatch, ValueError("GOOGLE_API_KEY nao configurada"))

    response, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.WAITING_AI
    assert document.error_code == "ai_unavailable"
    api = await client.get(
        f"/api/v1/documents/{response.id}",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert api.json()["error_code"] == "ai_unavailable"
    assert "GOOGLE_API_KEY" not in api.text


async def test_texto_cru_do_provedor_nunca_sai_na_api(db_session, monkeypatch, client):
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": RAW_429})
    response, _ = await _upload_async(db_session, user)

    api = await client.get(
        f"/api/v1/documents/{response.id}",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )

    assert api.status_code == 200
    assert "RESOURCE_EXHAUSTED" not in api.text
    assert "Quota exceeded" not in api.text
    assert api.json()["next_retry_at"]


async def test_documento_ilegivel_falha_sem_nova_tentativa(db_session, monkeypatch):
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": "Expecting value: line 1 column 1 (char 0)"})

    _, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "unreadable_document"
    assert document.next_retry_at is None


async def test_timeout_da_extracao_vira_fila(db_session, monkeypatch):
    user = await _user(db_session)
    monkeypatch.setattr(svc, "EXTRACTION_TIMEOUT_SECONDS", 0.01)

    async def slow(self, *args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(LLMOCRService, "extract_from_image", slow)

    _, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.WAITING_AI
    assert document.error_code == "ai_busy"


async def test_upload_sincrono_responde_202_quando_a_ia_esta_fora(db_session, monkeypatch, client):
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": RAW_429})

    response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
        files={"file": ("fatura.png", PNG, "image/png")},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "waiting_ai"
    assert body["error_code"] == "ai_quota_exhausted"
    assert "RESOURCE_EXHAUSTED" not in response.text


async def test_processamento_preso_volta_para_a_fila(db_session, monkeypatch):
    """Critério do #37: reiniciar no meio não deixa documento preso em processing."""
    user = await _user(db_session)
    calls = fake_ai(monkeypatch, OK)
    _, document = await _upload_async(db_session, user)
    assert calls == [1]
    # simula restart no meio de um processamento
    document.status = DocumentStatus.PROCESSING
    document.processing_started_at = utc_now() - timedelta(minutes=20)
    await db_session.commit()
    fake_ai(monkeypatch, OK)

    assert await svc.retry_waiting_documents() == 1
    await db_session.refresh(document)
    assert document.status == DocumentStatus.COMPLETED


async def test_processamento_preso_repetido_vira_failed(db_session, monkeypatch):
    user = await _user(db_session)
    fake_ai(monkeypatch, OK)
    _, document = await _upload_async(db_session, user)
    document.status = DocumentStatus.PROCESSING
    document.processing_started_at = utc_now() - timedelta(minutes=20)
    document.attempts = svc.MAX_STALE_ATTEMPTS - 1
    await db_session.commit()

    await svc.retry_waiting_documents()
    await db_session.refresh(document)

    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "processing_timeout"


async def test_arquivo_apagado_falha_com_codigo(db_session, monkeypatch):
    import os

    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": "503 UNAVAILABLE"})
    _, document = await _upload_async(db_session, user)
    os.remove(document.file_path)
    document.next_retry_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    assert await svc.retry_waiting_documents() == 0
    await db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "file_missing"


async def test_tentativas_tem_teto(db_session, monkeypatch):
    user = await _user(db_session)
    fake_ai(monkeypatch, {"items": [], "error": "503 UNAVAILABLE"})
    monkeypatch.setattr(svc, "MAX_AI_ATTEMPTS", 1)

    _, document = await _upload_async(db_session, user)

    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "ai_busy"


async def test_health_informa_o_estado_da_ia(client, isolated, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "ai_circuit", isolated)
    assert (await client.get("/health")).json()["ai"] == "ok"
    isolated.paused_until = utc_now() + timedelta(minutes=5)
    assert (await client.get("/health")).json()["ai"] == "quota_exhausted"


class _GenaiLike(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code} {message}")
        self.code = code


@pytest.mark.parametrize(
    "error,expected",
    [
        (_GenaiLike(429, "RESOURCE_EXHAUSTED"), AI_QUOTA_EXHAUSTED),
        (_GenaiLike(503, "UNAVAILABLE"), AI_BUSY),
        (_GenaiLike(504, "DEADLINE_EXCEEDED"), AI_BUSY),
        (_GenaiLike(403, "PERMISSION_DENIED"), AI_UNAVAILABLE),
        (_GenaiLike(400, "API key not valid"), AI_UNAVAILABLE),
        (TimeoutError(), AI_BUSY),
        ("Mistral API error: 429 rate limit", AI_QUOTA_EXHAUSTED),
        ("Google API error: 503", AI_BUSY),
        ("Expecting value: line 1 column 1", UNREADABLE_DOCUMENT),
        (None, UNREADABLE_DOCUMENT),
    ],
)
def test_classificacao(error, expected):
    assert classify(error) is expected


def test_backoff_cresce_e_tem_teto():
    now = utc_now()
    first = ai_failures.next_retry_at(AI_BUSY, 1, now) - now
    second = ai_failures.next_retry_at(AI_BUSY, 2, now) - now
    huge = ai_failures.next_retry_at(AI_BUSY, 30, now) - now
    assert first == AI_BUSY.retry_after
    assert second == AI_BUSY.retry_after * 2
    assert huge == ai_failures.MAX_RETRY_DELAY

"""Reenvio de documento duplicado (issue #36, N11).

Cobre: 409 no reenvio sem chamar a IA, force=true reprocessando o original,
indice unico (user_id, file_hash), exclusao que nao apaga arquivo de outro
documento e retry de documento sem arquivo retornando 410.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.modules.documents.services import document_service

PNG_CONTENT = b"\x89PNG\r\n\x1a\n conteudo de teste da fatura"


@pytest.fixture
def ai_calls(monkeypatch, tmp_path) -> list[int]:
    """Substitui a chamada a IA (sync e async) por um contador e isola a pasta de uploads."""
    calls: list[int] = []

    async def fake_background(document_id, *args, **kwargs):
        calls.append(document_id)

    async def fake_process(self, document, content, password=None):
        calls.append(document.id)
        document.status = DocumentStatus.COMPLETED
        return None

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(document_service, "process_document_background", fake_background)
    monkeypatch.setattr(document_service.DocumentService, "_process_document", fake_process)
    return calls


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: User) -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: test_user
    return client


async def _count_documents(db: AsyncSession, user: User) -> int:
    return await db.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user.id)
    )


def _png():
    return {"file": ("fatura.png", PNG_CONTENT, "image/png")}


@pytest.mark.asyncio
async def test_reenvio_async_retorna_409_sem_chamar_ia(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User, ai_calls: list[int]
):
    first = await auth_client.post("/api/v1/documents/async", files=_png())
    assert first.status_code == 202
    original_id = first.json()["id"]

    second = await auth_client.post("/api/v1/documents/async", files=_png())

    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "duplicate"
    assert second.json()["detail"]["document_id"] == original_id
    assert ai_calls == [original_id]
    assert await _count_documents(db_session, test_user) == 1


@pytest.mark.asyncio
async def test_reenvio_sync_retorna_409_sem_chamar_ia(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User, ai_calls: list[int]
):
    first = await auth_client.post("/api/v1/documents", files=_png())
    assert first.status_code == 201
    original_id = first.json()["id"]

    second = await auth_client.post("/api/v1/documents", files=_png())

    assert second.status_code == 409
    assert second.json()["detail"]["document_id"] == original_id
    assert ai_calls == [original_id]
    assert await _count_documents(db_session, test_user) == 1


@pytest.mark.asyncio
async def test_force_reprocessa_documento_original(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    ai_calls: list[int],
):
    first = await auth_client.post("/api/v1/documents", files=_png())
    original_id = first.json()["id"]

    forced = await auth_client.post("/api/v1/documents?force=true", files=_png())

    assert forced.status_code == 201
    assert forced.json()["id"] == original_id
    assert ai_calls == [original_id, original_id]
    assert await _count_documents(db_session, test_user) == 1


@pytest.mark.asyncio
async def test_indice_unico_impede_mesmo_hash_para_o_mesmo_usuario(
    db_session: AsyncSession, test_user: User
):
    for _ in range(2):
        db_session.add(
            Document(
                user_id=test_user.id,
                file_path="/tmp/a.png",
                file_hash="b" * 64,
                file_size=10,
                mime_type="image/png",
                original_filename="a.png",
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_excluir_documento_nao_apaga_arquivo_de_outro_documento(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    tmp_path,
):
    """Duplicatas antigas apontam para o mesmo arquivo; so o ultimo a sair apaga."""
    shared_file = tmp_path / "compartilhado.png"
    shared_file.write_bytes(PNG_CONTENT)
    docs = [
        Document(
            user_id=test_user.id,
            file_path=str(shared_file),
            file_hash=char * 64,
            file_size=len(PNG_CONTENT),
            mime_type="image/png",
            original_filename="fatura.png",
            status=DocumentStatus.COMPLETED,
        )
        for char in ("c", "d")
    ]
    db_session.add_all(docs)
    await db_session.flush()

    response = await auth_client.delete(f"/api/v1/documents/{docs[1].id}")
    assert response.status_code == 204
    assert shared_file.exists()

    response = await auth_client.delete(f"/api/v1/documents/{docs[0].id}")
    assert response.status_code == 204
    assert not shared_file.exists()


@pytest.mark.asyncio
async def test_retry_de_documento_sem_arquivo_retorna_410(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    tmp_path,
    ai_calls: list[int],
):
    document = Document(
        user_id=test_user.id,
        file_path=str(tmp_path / "nao-existe.png"),
        file_hash="e" * 64,
        file_size=10,
        mime_type="image/png",
        original_filename="fatura.png",
        status=DocumentStatus.FAILED,
    )
    db_session.add(document)
    await db_session.flush()

    response = await auth_client.post(f"/api/v1/documents/{document.id}/retry")

    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "file_missing"
    assert ai_calls == []

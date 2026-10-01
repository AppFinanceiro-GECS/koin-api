"""
O upload assíncrono agenda o processamento numa tarefa que abre a própria sessão do banco.
O documento precisa estar gravado (commit) quando a tarefa é agendada: com FastAPI >= 0.120 ela
pode começar antes do commit automático do fim da requisição, e o documento "não existia".
"""

import io

from fastapi import BackgroundTasks, UploadFile

from app.core.config import settings
from app.models.user import User
from app.modules.documents.services.document_service import DocumentService

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


async def test_upload_async_grava_o_documento_antes_de_agendar(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    user = User(email="upload@example.com", name="Upload", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    tasks = BackgroundTasks()
    file = UploadFile(file=io.BytesIO(PNG), filename="fatura.png")
    response = await DocumentService(db_session).upload_async(user, file, tasks)

    # Nada pendente na sessão da requisição: o documento já foi gravado (commit) quando a
    # tarefa foi agendada. No SQLite em memória dos testes as sessões dividem a conexão,
    # então ler por outra sessão não provaria o commit.
    assert not db_session.in_transaction()
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args[0] == response.id

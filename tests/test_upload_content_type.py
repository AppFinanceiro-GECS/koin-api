"""Upload pelo conteúdo do arquivo (issue #35).

Os cinco casos da evidência de homologação: HEIC, WEBP, PNG sem extensão,
script renomeado para .png e arquivo de 11 MB.
"""

import io
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app
from app.models.document import Document
from app.models.user import User
from app.modules.documents.services import document_service
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.upload_files import prepare_upload

ELEVEN_MB = 11 * 1024 * 1024
SHELL = b"#!/bin/sh\necho invasao\n"


def _image(fmt: str, size: tuple[int, int] = (8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (12, 80, 160)).save(buffer, format=fmt)
    return buffer.getvalue()


def _heic() -> bytes:
    import pillow_heif

    buffer = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (8, 8), (12, 80, 160))).save(buffer, quality=50)
    return buffer.getvalue()


def _upload(
    filename: str, content: bytes, content_type: str = "application/octet-stream"
) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers={"content-type": content_type},
    )


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(document_service, "process_document_background", _noop)
    return tmp_path


async def _noop(*args, **kwargs):
    return None


@pytest.fixture
def auth_client(client: AsyncClient, test_user: User) -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: test_user
    return client


async def _post_async(auth_client: AsyncClient, filename: str, content: bytes):
    return await auth_client.post(
        "/api/v1/documents/async",
        files={"file": (filename, content, "application/octet-stream")},
    )


@pytest.mark.asyncio
async def test_heic_de_iphone_entra_e_vai_para_a_ia_como_jpeg(
    auth_client, db_session: AsyncSession, upload_dir
):
    response = await _post_async(auth_client, "IMG_0001.HEIC", _heic())

    assert response.status_code == 202
    document = await db_session.get(Document, response.json()["id"])
    stored = Path(document.file_path).read_bytes()
    assert document.mime_type == "image/jpeg"
    assert stored.startswith(b"\xff\xd8")
    assert document.original_filename == "IMG_0001.HEIC"


@pytest.mark.asyncio
async def test_webp_entra_e_vai_para_a_ia_como_jpeg(auth_client, db_session, upload_dir):
    response = await _post_async(auth_client, "foto.webp", _image("WEBP"))

    assert response.status_code == 202
    document = await db_session.get(Document, response.json()["id"])
    assert document.mime_type == "image/jpeg"
    assert Path(document.file_path).read_bytes().startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_png_sem_extensao_entra(auth_client, db_session, upload_dir):
    png = _image("PNG")
    response = await _post_async(auth_client, "foto", png)

    assert response.status_code == 202
    document = await db_session.get(Document, response.json()["id"])
    assert document.mime_type == "image/png"
    assert document.file_path.endswith(".png")
    assert Path(document.file_path).read_bytes() == png


@pytest.mark.asyncio
async def test_script_renomeado_para_png_e_recusado(auth_client, upload_dir):
    response = await _post_async(auth_client, "malware.png", SHELL)

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "Tipo de arquivo não suportado. Envie JPEG, PNG, WEBP, HEIC, PDF ou planilha."
    )
    assert list(Path(upload_dir).rglob("*")) == []


@pytest.mark.asyncio
async def test_arquivo_de_11mb_responde_413(auth_client, upload_dir):
    response = await _post_async(auth_client, "grande.png", b"x" * ELEVEN_MB)

    assert response.status_code == 413
    assert response.json()["detail"] == "Arquivo muito grande. Máximo: 10MB"
    assert list(Path(upload_dir).rglob("*")) == []


@pytest.mark.parametrize("method", ["upload", "upload_async", "upload_batch"])
async def test_os_tres_uploads_recusam_tipo_e_tamanho(db_session, test_user, upload_dir, method):
    service = DocumentService(db_session)

    script = _upload("malware.png", SHELL, "image/png")
    script_args = [test_user, [script]] if method == "upload_batch" else [test_user, script]
    if method == "upload_async":
        script_args.append(BackgroundTasks())
    with pytest.raises(HTTPException) as script_error:
        await getattr(service, method)(*script_args)
    assert script_error.value.status_code == 415

    huge = _upload("grande.png", b"x" * ELEVEN_MB)
    huge_args = [test_user, [huge]] if method == "upload_batch" else [test_user, huge]
    if method == "upload_async":
        huge_args.append(BackgroundTasks())
    with pytest.raises(HTTPException) as huge_error:
        await getattr(service, method)(*huge_args)
    assert huge_error.value.status_code == 413


async def test_imagem_grande_fica_com_lado_de_no_maximo_2000px():
    prepared = await prepare_upload(_upload("grande.jpg", _image("JPEG", (3000, 1200))))

    with Image.open(io.BytesIO(prepared.content)) as image:
        assert image.size == (2000, 800)
    assert prepared.mime_type == "image/jpeg"


async def test_planilha_csv_continua_aceita_pelo_nome_e_pelo_texto():
    prepared = await prepare_upload(
        _upload("gastos.csv", b"data,valor\n2026-01-01,10\n", "text/csv")
    )

    assert prepared.extension == "csv"
    assert prepared.mime_type == "text/csv"

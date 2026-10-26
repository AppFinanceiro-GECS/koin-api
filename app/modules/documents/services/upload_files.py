"""Prepara um upload pelo conteúdo do arquivo, não pelo nome."""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

import filetype
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

MAX_IMAGE_SIDE = 2000

_HEIF_BRANDS = {
    b"heic": ("heic", "image/heic"),
    b"heix": ("heic", "image/heic"),
    b"hevc": ("heic", "image/heic"),
    b"heim": ("heic", "image/heic"),
    b"heis": ("heic", "image/heic"),
    b"heif": ("heif", "image/heif"),
    b"mif1": ("heif", "image/heif"),
    b"msf1": ("heif", "image/heif"),
}

_BY_EXTENSION = {
    "jpg": ("jpg", "image/jpeg"),
    "jpeg": ("jpg", "image/jpeg"),
    "png": ("png", "image/png"),
    "webp": ("webp", "image/webp"),
    "heic": ("heic", "image/heic"),
    "heif": ("heif", "image/heif"),
    "pdf": ("pdf", "application/pdf"),
}

_CONVERT_TO_JPEG = {"heic", "heif", "webp"}

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLS_MIME = "application/vnd.ms-excel"


class UnreadableImage(Exception):
    """HEIC ou WEBP cujo conteúdo não abre como imagem."""


@dataclass(frozen=True)
class PreparedUpload:
    content: bytes
    extension: str
    mime_type: str
    original_filename: str
    original_size: int


def _unsupported(images_only: bool) -> HTTPException:
    if images_only:
        detail = "Tipo de arquivo não suportado. Envie uma imagem JPEG, PNG, WEBP ou HEIC."
    else:
        detail = "Tipo de arquivo não suportado. Envie JPEG, PNG, WEBP, HEIC, PDF ou planilha."
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


def _too_large(limit_mb: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"Arquivo muito grande. Máximo: {limit_mb}MB",
    )


def _filename_ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower()


def _heif_brand(content: bytes) -> tuple[str, str] | None:
    if len(content) < 12 or content[4:8] != b"ftyp":
        return None
    return _HEIF_BRANDS.get(content[8:12])


def _looks_like_text(content: bytes) -> bool:
    sample = content[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("cp1252")
        except UnicodeDecodeError:
            return False
    return True


def _spreadsheet(content: bytes, filename: str | None) -> tuple[str, str] | None:
    """CSV e Excel não têm assinatura exclusiva. O nome desempata o conteúdo compatível."""
    ext = _filename_ext(filename)
    if ext == "csv" and _looks_like_text(content):
        return "csv", "text/csv"
    if ext == "xlsx" and content.startswith(b"PK\x03\x04"):
        return "xlsx", _XLSX_MIME
    if ext == "xls" and content.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls", _XLS_MIME
    return None


def detect_type(content: bytes, filename: str | None, *, images_only: bool) -> tuple[str, str]:
    if not content:
        raise _unsupported(images_only)

    heif = _heif_brand(content)
    if heif is not None:
        return heif

    kind = filetype.guess(content)
    if kind is not None:
        mapped = _BY_EXTENSION.get(kind.extension)
        if mapped is not None:
            return mapped

    if not images_only:
        sheet = _spreadsheet(content, filename)
        if sheet is not None:
            return sheet

    raise _unsupported(images_only)


def _load_image(content: bytes) -> Image.Image:
    import pillow_heif

    pillow_heif.register_heif_opener()
    image = Image.open(io.BytesIO(content))
    image.load()
    transposed = ImageOps.exif_transpose(image)
    return transposed if transposed is not None else image


def _normalize_image(content: bytes, extension: str, mime: str) -> tuple[bytes, str, str]:
    must_convert = extension in _CONVERT_TO_JPEG
    try:
        image = _load_image(content)
    except Image.DecompressionBombError:
        raise UnreadableImage
    except (UnidentifiedImageError, OSError, ValueError):
        if must_convert:
            raise UnreadableImage
        return content, extension, mime

    too_big = max(image.size) > MAX_IMAGE_SIDE
    if not must_convert and not too_big:
        return content, extension, mime

    if too_big:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)

    if must_convert or extension == "jpg":
        if image.mode != "RGB":
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
        return output.getvalue(), "jpg", "image/jpeg"

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), "png", "image/png"


async def _read_limited(file: UploadFile) -> tuple[bytes, int]:
    max_size = settings.max_upload_size_mb * 1024 * 1024
    size: int | None
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    except (OSError, AttributeError):
        size = None

    if size is not None and size > max_size:
        raise _too_large(settings.max_upload_size_mb)

    content = await file.read()
    if len(content) > max_size:
        raise _too_large(settings.max_upload_size_mb)
    return content, len(content)


async def prepare_upload(file: UploadFile, *, images_only: bool = False) -> PreparedUpload:
    content, original_size = await _read_limited(file)
    extension, mime = detect_type(content, file.filename, images_only=images_only)
    if mime.startswith("image/"):
        try:
            content, extension, mime = await asyncio.to_thread(
                _normalize_image, content, extension, mime
            )
        except UnreadableImage:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Não foi possível ler a imagem.",
            ) from None
    return PreparedUpload(
        content=content,
        extension=extension,
        mime_type=mime,
        original_filename=file.filename or "arquivo",
        original_size=original_size,
    )

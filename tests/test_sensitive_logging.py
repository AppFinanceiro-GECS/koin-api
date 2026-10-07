"""Issue #48: logs must not expose PDF credentials or extracted financial data."""

import ast
import copy
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import fitz
import pytest
from fastapi import BackgroundTasks, UploadFile

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.modules.documents.routers import documents
from app.modules.documents.services import llm_ocr_service
from app.modules.documents.services.document_classifier import DocumentClassifier, DocumentType
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.extraction_validator import ExtractionValidator
from app.modules.documents.services.pdf_converter import convert_pdf_to_images_sync
from app.modules.documents.services.pdf_text_extractor import PDFTextExtractor
from app.modules.documents.services.providers.google_provider import GoogleProvider
from app.modules.documents.services.providers.mistral_provider import MistralProvider
from app.modules.documents.services.response_parser import ResponseParser

PASSWORD = "Zq8_PASSWORD_SECRET_918273"
MERCHANT = "MERCHANT_SECRET_NEBULA"
TOKEN = "TOKEN_SECRET_ABC987"
CARD = "CARD_SUFFIX_SECRET_7421"
DATE = "2031-07-19"
AMOUNT = 12345.67
ERROR = f"{PASSWORD} {TOKEN} Authorization: Bearer {TOKEN} {MERCHANT} {AMOUNT}"
APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(autouse=True)
def private_output(capsys, caplog, monkeypatch):
    """Capture both streams and all application log levels, including DEBUG."""
    caplog.set_level(logging.DEBUG, logger="app")
    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(settings, "mistral_api_key", None)
    yield
    output = capsys.readouterr()
    text = output.out + output.err + caplog.text
    for secret in (
        PASSWORD,
        PASSWORD[:3],
        TOKEN,
        MERCHANT,
        CARD,
        "7421",
        DATE,
        "12345.67",
        "12345,67",
        "12.345,67",
        "9876.54",
        "22222.21",
        "ADDITIONAL_SECRET_ITEM",
        "2031-08-23",
    ):
        assert secret not in text
    assert output.out == ""
    assert output.err == ""
    assert all(record.exc_info is None for record in caplog.records)


@pytest.fixture
def extracted():
    return {
        "document_type": "fatura_cartao",
        "total_amount": 22222.21,
        "items": [
            {"description": MERCHANT, "amount": AMOUNT, "date": DATE},
            {"description": "ADDITIONAL_SECRET_ITEM", "amount": 9876.54, "date": DATE},
        ],
        "card_info": {
            "card_last_digits": CARD,
            "total_amount": 22222.21,
            "due_date": "2031-08-23",
        },
        "payment_info": {
            "total": 22222.21,
            "payments": [{"method": "pix", "amount": 22222.21}],
        },
    }


def pdf_bytes(password=None):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 50), f"{MERCHANT} {AMOUNT} {DATE} {CARD}")
        if password:
            return pdf.tobytes(
                encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner-only-synthetic",
                user_pw=password,
            )
        return pdf.tobytes()


@pytest.mark.parametrize("password", [PASSWORD, "J9!"])
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_upload_passes_password_without_logging(
    password, asynchronous, monkeypatch, capsys, caplog
):
    result = object()
    upload = AsyncMock(return_value=result)
    method = "upload_async" if asynchronous else "upload"
    monkeypatch.setattr(DocumentService, method, upload)
    file = UploadFile(file=io.BytesIO(b"pdf"), filename="invoice.pdf")
    kwargs = dict(
        current_user=object(),
        db=object(),
        file=file,
        password=password,
        credit_card_id=None,
        force=False,
    )
    if asynchronous:
        kwargs["background_tasks"] = BackgroundTasks()
        actual = await documents.upload_document_async(**kwargs)
        assert upload.await_args.args[3] == password
    else:
        actual = await documents.upload_document(**kwargs)
        assert upload.await_args.args[2] == password
    assert actual is result
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert password not in caplog.text
    assert password[:3] not in caplog.text


@pytest.mark.parametrize("correct", [True, False])
def test_encrypted_pdf_still_authenticates_without_logging(correct):
    content = pdf_bytes(PASSWORD)
    images, error = convert_pdf_to_images_sync(content, PASSWORD if correct else "wrong")
    if correct:
        assert error is None
        assert len(images) == 1
        text = PDFTextExtractor.extract_text_with_layout(content, PASSWORD)
        assert MERCHANT in text
    else:
        assert images == []
        assert error == "Senha incorreta"


@pytest.mark.parametrize("document_type", ["fatura_cartao", "cupom_fiscal"])
def test_parser_and_validator_preserve_data_without_dumping(extracted, document_type, caplog):
    extracted["document_type"] = document_type
    raw = json.dumps(extracted)
    result = ResponseParser().parse(raw)
    assert result["items"][0]["description"] == MERCHANT
    assert result["items"][0]["amount"] == AMOUNT
    assert result["items"][0]["date"] == DATE
    assert result["card_info"]["card_last_digits"] == "7421"
    cleaned = ExtractionValidator().validate_and_clean(
        result["items"], result["card_info"], document_type, extracted["total_amount"]
    )
    assert cleaned[0]["description"] == MERCHANT
    assert cleaned[0]["amount"] == AMOUNT
    assert raw not in caplog.text
    assert "2031-08-23" not in caplog.text


def test_validator_duplicate_cleanup_does_not_log_purchase(extracted):
    item = extracted["items"][0]
    result = ExtractionValidator().deduplicate_consecutive_items([item, copy.deepcopy(item)])
    assert result == [item]


@pytest.mark.parametrize("mode", ["image", "text", "native", "multi"])
async def test_google_pipeline_does_not_log_response_or_pdf(extracted, mode, monkeypatch, tmp_path):
    service = llm_ocr_service.LLMOCRService(provider="google", model="safe-model")
    provider = service._get_provider()
    monkeypatch.setattr(provider, "_get_client", lambda: object())
    generate = Mock(return_value=SimpleNamespace(text=json.dumps(extracted)))
    monkeypatch.setattr(provider, "_generate_content_sync", generate)
    monkeypatch.setattr(settings, "google_pdf_mode", mode if mode in ("text", "native") else "text")
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    if mode == "multi":
        result = await service.extract_from_multiple_images([(b"image", "image/png")])
    elif mode == "image":
        result = await service.extract_from_image(b"image", "image/png")
    else:
        password = PASSWORD if mode == "text" else None
        result = await service.extract_from_image(
            pdf_bytes(password), "application/pdf", password=password
        )
    assert generate.call_count == 1
    assert result["items"][0]["description"] == MERCHANT
    assert result["items"][0]["amount"] == AMOUNT


@pytest.mark.parametrize("multiple", [False, True])
async def test_ocr_exception_logs_only_error_type(multiple, monkeypatch, caplog):
    service = llm_ocr_service.LLMOCRService(provider="google")
    provider = SimpleNamespace(
        extract_from_image=AsyncMock(side_effect=RuntimeError(ERROR)),
        extract_multi_page=AsyncMock(side_effect=RuntimeError(ERROR)),
    )
    monkeypatch.setattr(service, "_get_provider", lambda: provider)
    if multiple:
        result = await service.extract_from_multiple_images([(b"image", "image/png")])
    else:
        result = await service.extract_from_image(b"image", "image/png")
    assert result["error"] == ERROR  # Existing return contract is unchanged.
    assert "error_type=RuntimeError" in caplog.text


async def test_pdf_fallback_keeps_password_and_sanitizes_primary_error(extracted, monkeypatch):
    service = llm_ocr_service.LLMOCRService(provider="google")
    primary = SimpleNamespace(extract_from_pdf=AsyncMock(side_effect=RuntimeError(ERROR)))
    fallback = SimpleNamespace(extract_from_pdf=AsyncMock(return_value=extracted))
    monkeypatch.setattr(service, "_get_provider", lambda: primary)
    monkeypatch.setattr(service, "_get_fallback_provider", lambda: fallback)
    result = await service.extract_from_image(b"pdf", "application/pdf", password=PASSWORD)
    assert primary.extract_from_pdf.await_args.args[-1] == PASSWORD
    assert fallback.extract_from_pdf.await_args.args[-1] == PASSWORD
    assert result["items"][0]["description"] == MERCHANT


async def test_google_retry_logs_type_without_exception_message(monkeypatch, caplog):
    provider = GoogleProvider(parse_response_fn=ResponseParser().parse)
    monkeypatch.setattr(provider, "_get_client", lambda: object())
    provider.retry_delay = 0
    generate = Mock(side_effect=RuntimeError("503 " + ERROR))
    monkeypatch.setattr(provider, "_generate_content_sync", generate)
    with pytest.raises(RuntimeError):
        await provider.extract_multi_page([(b"image", "image/png")])
    assert generate.call_count == provider.max_retries
    assert "error_type=RuntimeError" in caplog.text


@pytest.mark.parametrize("fails", [False, True])
async def test_mistral_annotation_and_errors_do_not_leak(extracted, fails, monkeypatch, caplog):
    provider = MistralProvider(parse_response_fn=ResponseParser().parse, use_classifier=False)
    response = SimpleNamespace(
        pages=[SimpleNamespace(markdown=f"{MERCHANT} {AMOUNT} {DATE}")],
        document_annotation=json.dumps(extracted),
    )
    call = Mock(side_effect=RuntimeError(ERROR)) if fails else Mock(return_value=response)
    monkeypatch.setattr(provider, "_ocr_with_annotation_sync", call)
    result, text = await provider._try_annotation_extraction(
        object(), SimpleNamespace(id="file-id")
    )
    assert call.call_count == 1
    if fails:
        assert result is None
        assert "error_type=RuntimeError" in caplog.text
    else:
        assert result["items"][0]["description"] == MERCHANT
        assert MERCHANT in text


@pytest.mark.parametrize("fails", [False, True])
async def test_classifier_never_logs_raw_response(fails, monkeypatch):
    from google import genai

    generate = (
        Mock(side_effect=RuntimeError(ERROR))
        if fails
        else Mock(return_value=SimpleNamespace(text=ERROR))
    )
    monkeypatch.setattr(
        genai,
        "Client",
        lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    monkeypatch.setattr(settings, "google_api_key", TOKEN)
    result = await DocumentClassifier()._classify_by_llm(MERCHANT)
    assert result == DocumentType.UNKNOWN
    assert generate.call_count == 1


@pytest.mark.parametrize("fails", [False, True])
async def test_document_status_logs_id_and_count_without_error_payload(
    extracted, fails, monkeypatch, caplog
):
    db = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
    service = DocumentService(db)
    document = Document(id=823, user_id=1, original_filename=MERCHANT, mime_type="application/pdf")
    extract = (
        AsyncMock(side_effect=ValueError(ERROR)) if fails else AsyncMock(return_value=extracted)
    )
    monkeypatch.setattr(service, "_extract_data", extract)
    result = await service._process_document(document, b"pdf", PASSWORD)
    assert extract.await_args.args[-1] == PASSWORD
    if fails:
        assert document.status == DocumentStatus.FAILED
        assert result is None
        assert "error_type=ValueError" in caplog.text
    else:
        assert document.status == DocumentStatus.COMPLETED
        assert result is extracted
        assert "document_id=823" in caplog.text
        assert "item_count=2" in caplog.text


def test_no_executable_print_in_app():
    offenders = []
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Name)
                and node.func.id == "print"
                or isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "builtins"
                and node.func.attr == "print"
            ):
                offenders.append(f"{path.relative_to(APP)}:{node.lineno}")
    assert offenders == []


def test_document_logs_do_not_attach_tracebacks():
    offenders = []
    for path in (APP / "modules" / "documents").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            unsafe = name in {"traceback.print_exc", "traceback.format_exc", "logger.exception"}
            unsafe |= name.startswith("logger.") and any(
                k.arg == "exc_info"
                and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                for k in node.keywords
            )
            if unsafe:
                offenders.append(f"{path.relative_to(APP)}:{node.lineno}")
    assert offenders == []

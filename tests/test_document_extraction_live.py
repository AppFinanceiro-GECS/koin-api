"""Eight real Google extraction cases. Disabled unless --run-live is supplied."""

import io
import json
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tests.document_benchmark import BenchmarkRecord

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "documents"
MODELS = [
    pytest.param("gemini-3.8-flash", id="flash"),
    pytest.param("gemini-3.5-flash-lite", id="flash-lite"),
]
DOCUMENTS = ["itau_two_columns.pdf", "nubank.pdf", "bradesco.pdf", "cupom_fiscal.png"]


@pytest.mark.live
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("filename", DOCUMENTS)
async def test_document_extraction_live(filename, model, monkeypatch, live_benchmark):
    from app.core.config import settings
    from app.modules.documents.services import llm_ocr_service
    from app.modules.documents.services.providers.google_provider import GoogleProvider

    if not settings.google_api_key or not settings.google_api_key.strip():
        pytest.skip("GOOGLE_API_KEY is required for the Google extraction benchmark.")
    pytest.importorskip("google.genai", reason="The declared Google GenAI SDK is required.")

    start = time.perf_counter()
    try:
        # Discard provider debug output, including raw AI responses and exception URLs.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            # Preserve the real pipeline and prevent any Mistral fallback.
            monkeypatch.setattr(settings, "mistral_api_key", None)

            def forbid_mistral(*args, **kwargs):
                raise AssertionError("Mistral fallback is forbidden in the Gemini benchmark.")

            monkeypatch.setattr(llm_ocr_service, "MistralProvider", forbid_mistral)
            service = llm_ocr_service.LLMOCRService(provider="google", model=model)
            assert isinstance(service._get_provider(), GoogleProvider)
            assert service._get_provider().model == model
            assert service._get_fallback_provider() is None

            path = FIXTURES_DIR / filename
            expected = json.loads(path.with_suffix(".expected.json").read_text(encoding="utf-8"))
            content = path.read_bytes()
            mime_type = "application/pdf" if path.suffix == ".pdf" else "image/png"
            result = await service.extract_from_image(content, mime_type, filename=filename)
    except Exception as exc:
        record = BenchmarkRecord.from_exception(filename, model, time.perf_counter() - start, exc)
    else:
        record = BenchmarkRecord.from_result(
            filename, model, time.perf_counter() - start, result, expected
        )
    live_benchmark.append(record)
    if record.status == "technical_error":
        pytest.fail(f"technical_error: {record.error_type}", pytrace=False)
    assert record.comparison.passed, record.comparison.failure_message()

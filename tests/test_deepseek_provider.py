"""Testes para o DeepSeekProvider e integracao com vision (deepseek-flash)"""

import json

import httpx
import pytest

from app.modules.documents.services.llm_ocr_service import LLMOCRService
from app.modules.documents.services.providers.deepseek_provider import DeepSeekProvider


def test_deepseek_provider_init():
    provider = DeepSeekProvider()
    assert provider.model == "deepseek-flash"
    assert provider.max_retries == 3


@pytest.mark.asyncio
async def test_deepseek_extract_from_image_payload(monkeypatch):
    """Verifica se o payload enviado para o DeepSeek tem a estrutura de vision compativel"""
    captured_requests = []

    def mock_post(url, headers, json):
        captured_requests.append({"url": url, "headers": headers, "json": json})
        response_body = {
            "choices": [
                {
                    "message": {
                        "content": json_dumps(
                            {
                                "document_type": "fatura_cartao",
                                "items": [{"description": "Uber", "amount": 25.50}],
                            }
                        )
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
            },
        }
        return httpx.Response(200, json=response_body)

    json_dumps = json.dumps

    from app.modules.documents.services.providers import deepseek_provider

    monkeypatch.setattr(
        deepseek_provider.settings,
        "deepseek_api_key",
        "sk-test-key",
    )
    monkeypatch.setattr(
        deepseek_provider.settings,
        "deepseek_base_url",
        "https://api.deepseek.com",
    )

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockAsyncClient())

    provider = DeepSeekProvider(
        model="deepseek-flash",
        prompt="Extraia os dados",
        parse_response_fn=lambda x: json.loads(x),
    )

    fake_image_bytes = b"fake_png_data"
    result = await provider.extract_from_image(fake_image_bytes, "image/png")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://api.deepseek.com/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer sk-test-key"
    assert req["json"]["model"] == "deepseek-flash"

    # Checa formato multimodal / vision
    content = req["json"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Extraia os dados"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    # Checa resultado retornado
    assert result["document_type"] == "fatura_cartao"
    assert len(result["items"]) == 1
    assert result["items"][0]["description"] == "Uber"


@pytest.mark.asyncio
async def test_deepseek_extract_multi_page(monkeypatch):
    """Verifica envio de múltiplas páginas para o DeepSeek"""
    captured_requests = []

    def mock_post(url, headers, payload):
        captured_requests.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"items": [{"description": "Item 1"}]})}}
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 30},
            },
        )

    from app.modules.documents.services.providers import deepseek_provider

    monkeypatch.setattr(deepseek_provider.settings, "deepseek_api_key", "sk-test-key")

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockAsyncClient())

    provider = DeepSeekProvider(
        parse_response_fn=lambda x: json.loads(x),
    )

    pages = [(b"page1", "image/png"), (b"page2", "image/png")]
    result = await provider.extract_multi_page(pages)

    assert len(captured_requests) == 1
    req_json = captured_requests[0]
    content = req_json["messages"][0]["content"]
    # 1 prompt text + 2 images
    assert len(content) == 3
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[2]["type"] == "image_url"
    assert result["items"][0]["description"] == "Item 1"


def test_llm_ocr_service_resolves_deepseek(monkeypatch):
    """Garante que LLMOCRService instancia DeepSeekProvider quando provider='deepseek'"""
    service = LLMOCRService(provider="deepseek", model="deepseek-flash")
    provider = service._get_provider()
    assert isinstance(provider, DeepSeekProvider)
    assert provider.model == "deepseek-flash"

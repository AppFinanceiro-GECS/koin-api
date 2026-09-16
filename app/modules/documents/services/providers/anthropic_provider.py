"""Anthropic Claude provider para extracao de documentos"""

import asyncio
import base64

from app.core.config import settings

from .base import BaseProvider

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0


class AnthropicProvider(BaseProvider):
    """Provider Anthropic Claude para extracao de documentos"""

    def __init__(self, model: str | None = None, prompt: str = "", parse_response_fn=None):
        super().__init__(model or "claude-3-sonnet-20240229")
        self.max_retries = DEFAULT_MAX_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.prompt = prompt
        self._parse_response = parse_response_fn or (lambda x: {"items": [], "error": "No parser"})

    async def extract_from_image(self, image_content: bytes, mime_type: str) -> dict:
        """Extrai dados de uma imagem usando Anthropic Claude"""
        import httpx

        api_key = settings.anthropic_api_key
        if not api_key:
            return {"items": [], "error": "ANTHROPIC_API_KEY nao configurada"}

        image_base64 = base64.b64encode(image_content).decode("utf-8")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "max_tokens": 4000,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": mime_type,
                                                "data": image_base64,
                                            },
                                        },
                                        {"type": "text", "text": self.prompt},
                                    ],
                                }
                            ],
                        },
                    )

                    if response.status_code != 200:
                        error_msg = f"Anthropic API error: {response.status_code}"
                        if response.status_code in [503, 429]:
                            raise Exception(error_msg)
                        return {"items": [], "error": error_msg}

                    result = response.json()
                    content = result["content"][0]["text"]
                    return self._parse_response(content)

            except Exception as e:
                last_error = e
                if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    await asyncio.sleep(wait_time)
                    continue
                elif "httpx" not in str(type(e).__module__):
                    raise

        return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

    async def extract_from_pdf(
        self, pdf_content: bytes, filename: str = "document.pdf", password: str | None = None
    ) -> dict:
        """Anthropic nao suporta PDF direto - retorna None para usar fallback"""
        return None

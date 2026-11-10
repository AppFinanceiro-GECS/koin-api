"""DeepSeek provider para extracao de documentos"""

import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path

from app.core.ai_usage import AIUnavailable, tracked_call
from app.core.config import settings

from .base import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0


class DeepSeekProvider(BaseProvider):
    """Provider DeepSeek (deepseek-flash com suporte a visao) para extracao de documentos"""

    def __init__(
        self,
        model: str | None = None,
        prompt: str = "",
        parse_response_fn=None,
    ):
        super().__init__(model or settings.vision_model or "deepseek-flash")
        self.max_retries = DEFAULT_MAX_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.base_prompt = prompt
        self.prompt = prompt
        self._parse_response = parse_response_fn or (lambda x: {"items": [], "error": "No parser"})

    def _detect_bank(self, text: str) -> str | None:
        """Detecta o banco emissor da fatura a partir do texto."""
        text_lower = text.lower()
        bank_indicators = {
            "itau": ["banco itau", "itaú", "itau unibanco", "financeira itau cbd"],
            "nubank": ["nubank", "nu pagamentos"],
            "bradesco": ["bradesco", "banco bradesco"],
            "santander": ["santander", "banco santander"],
            "inter": ["banco inter", "inter"],
            "c6": ["c6 bank", "banco c6", "c6bank"],
            "picpay": ["picpay", "pic pay"],
            "neon": ["neon", "banco neon"],
            "next": ["next", "banco next"],
            "will": ["will bank", "banco will"],
            "pan": ["banco pan", "bancopan"],
        }
        for bank_name, indicators in bank_indicators.items():
            for indicator in indicators:
                if indicator in text_lower:
                    return bank_name
        return None

    def _compose_prompt_with_bank(self, bank_name: str | None) -> str:
        prompt_text = self.base_prompt
        if bank_name:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
            bank_prompt_path = prompts_dir / "banks" / f"{bank_name}.md"
            if bank_prompt_path.exists():
                bank_prompt = bank_prompt_path.read_text(encoding="utf-8")
                prompt_text = f"{prompt_text}\n\n{bank_prompt}"
        return prompt_text

    async def _call_api(self, messages: list[dict], response_format: dict | None = None) -> dict:
        import httpx

        api_key = settings.deepseek_api_key
        if not api_key:
            return {"items": [], "error": "DEEPSEEK_API_KEY nao configurada"}

        base_url = (settings.deepseek_base_url or "https://api.deepseek.com").rstrip("/")
        url = f"{base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.1,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await tracked_call(
                        "deepseek",
                        self.model,
                        lambda: client.post(
                            url,
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        ),
                        feature="extraction",
                    )

                    if response.status_code != 200:
                        error_text = response.text[:200]
                        error_msg = f"DeepSeek API error {response.status_code}: {error_text}"
                        if response.status_code in [503, 502, 429]:
                            raise Exception(error_msg)
                        return {"items": [], "error": error_msg}

                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return self._parse_response(content)

            except AIUnavailable:
                raise
            except Exception as e:
                last_error = e
                if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    logger.warning("[DeepSeekProvider] Retrying in %ss: %s", wait_time, e)
                    await asyncio.sleep(wait_time)
                    continue
                elif "httpx" not in str(type(e).__module__):
                    raise

        return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

    async def extract_from_image(self, image_content: bytes, mime_type: str) -> dict:
        """Extrai dados de imagem com deepseek-flash via vision"""
        image_base64 = base64.b64encode(image_content).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}",
                        },
                    },
                ],
            }
        ]
        return await self._call_api(messages)

    async def extract_multi_page(self, images: list[tuple[bytes, str]]) -> dict:
        """Extrai dados de multiplas paginas enviadas juntas para o modelo"""
        content_parts = [{"type": "text", "text": self.prompt}]
        for img_bytes, img_mime in images:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{img_mime};base64,{b64}"},
                }
            )
        messages = [{"role": "user", "content": content_parts}]
        return await self._call_api(messages)

    async def extract_from_pdf(
        self, pdf_content: bytes, filename: str = "document.pdf", password: str | None = None
    ) -> dict | None:
        """Extrai dados de PDF via PyMuPDF layout de texto estruturado.
        Retorna None se o PDF nao tiver texto para disparar conversao em imagens."""
        from ..pdf_text_extractor import PDFTextExtractor

        def _extract():
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(pdf_content)
                temp_path = f.name
            try:
                with open(temp_path, "rb") as f:
                    pdf_bytes = f.read()
                return PDFTextExtractor.extract_text_with_layout(pdf_bytes, password)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        try:
            ocr_text = await asyncio.to_thread(_extract)
        except AIUnavailable:
            raise
        except Exception as e:
            logger.info(
                "[DeepSeekProvider] Erro ao extrair texto do PDF: %s, fallback para imagem", e
            )
            return None

        if not ocr_text or len(ocr_text.strip()) < 50:
            logger.info(
                "[DeepSeekProvider] PDF sem texto legivel (< 50 chars), fallback para imagens"
            )
            return None

        bank_name = self._detect_bank(ocr_text)
        composed_prompt = self._compose_prompt_with_bank(bank_name)

        final_prompt = f"""{composed_prompt}

## TEXTO EXTRAÍDO DO DOCUMENTO
```
{ocr_text}
```

Agora extraia TODAS as transações deste texto.
⚠️ IMPORTANTE: Retorne um OBJETO JSON com esta estrutura:
{{
  "document_type": "fatura_cartao",
  "card_info": {{ ... }},
  "items": [{{ ... }}]
}}
NÃO retorne texto fora do JSON."""

        messages = [{"role": "user", "content": final_prompt}]
        return await self._call_api(messages)

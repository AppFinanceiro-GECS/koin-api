"""Google Gemini provider para extracao de documentos"""

import asyncio
import base64
import os
import tempfile

from app.core.config import settings

from .base import BaseProvider

# Configuracao de retry
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0


class GoogleProvider(BaseProvider):
    """Provider Google Gemini para extracao de documentos"""

    def __init__(
        self,
        model: str | None = None,
        prompt: str = "",
        response_schema=None,
        parse_response_fn=None,
    ):
        super().__init__(model or settings.vision_model or "gemini-2.0-flash")
        self.max_retries = DEFAULT_MAX_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY
        self._client = None
        self.base_prompt = prompt  # Prompt base (geral)
        self.prompt = prompt  # Prompt atual (pode ser composto)
        self.response_schema = response_schema
        self._parse_response = parse_response_fn or (lambda x: {"items": [], "error": "No parser"})

    def _detect_bank(self, text: str) -> str | None:
        """Detecta o banco emissor da fatura a partir do texto.

        Returns:
            Nome do banco em lowercase (ex: "itau", "nubank") ou None
        """
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
                    print(f"[GoogleProvider] Banco detectado: {bank_name}")
                    return bank_name

        return None

    def _compose_prompt_with_bank(self, bank_name: str | None) -> str:
        """Compõe prompt base + prompt específico do banco (se existir).

        Args:
            bank_name: Nome do banco detectado (ex: "itau")

        Returns:
            Prompt composto
        """
        from pathlib import Path

        prompt_text = self.base_prompt

        if bank_name:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
            bank_prompt_path = prompts_dir / "banks" / f"{bank_name}.md"

            if bank_prompt_path.exists():
                bank_prompt = bank_prompt_path.read_text(encoding="utf-8")
                prompt_text = f"{prompt_text}\n\n{bank_prompt}"
                print(f"[GoogleProvider] Prompt específico do banco '{bank_name}' adicionado")
            else:
                print(f"[GoogleProvider] Banco '{bank_name}' sem prompt específico")

        return prompt_text

    def _get_client(self):
        """Obtem cliente Google Genai (lazy initialization)"""
        if self._client is None:
            try:
                from google import genai

                api_key = settings.google_api_key
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY nao configurada")
                self._client = genai.Client(api_key=api_key)
            except ImportError:
                raise ImportError("google-genai nao instalado. Execute: pip install google-genai")
        return self._client

    def _generate_content_sync(self, client, model: str, contents, config):
        """Chamada sincrona ao Gemini (executada em thread separada)"""
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

    def _upload_file_sync(self, client, file_path: str, mime_type: str):
        """Upload sincrono de arquivo (executado em thread separada)"""
        return client.files.upload(
            file=file_path,
            config={"mime_type": mime_type},
        )

    async def extract_from_image(self, image_content: bytes, mime_type: str) -> dict:
        """Extrai dados de uma imagem usando Google Gemini (non-blocking)"""
        try:
            from google.genai import types
        except ImportError:
            return await self._call_httpx(image_content, mime_type)

        client = self._get_client()

        contents = [
            types.Part.from_bytes(data=image_content, mime_type=mime_type),
            self.prompt,
        ]
        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=16000,
        )

        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Executa em thread separada para nao bloquear o event loop
                response = await asyncio.to_thread(
                    self._generate_content_sync, client, self.model, contents, config
                )
                return self._parse_response(response.text)

            except Exception as e:
                last_error = e
                if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

    async def extract_from_pdf(
        self, pdf_content: bytes, filename: str = "document.pdf", password: str | None = None
    ) -> dict:
        """Extrai dados de um PDF via upload para o Gemini (non-blocking)"""
        try:
            from google.genai import types
        except ImportError:
            print("[GoogleProvider] google.genai not available, falling back to image conversion")
            return None  # Sinaliza para usar fallback

        client = self._get_client()

        # Auto-detect best PDF mode: native for banks with complex layouts, text for others
        use_native = settings.google_pdf_mode == "native"
        if not use_native:
            # Quick bank detection to auto-select native mode for complex layouts
            try:
                import fitz

                doc = fitz.open(stream=pdf_content, filetype="pdf")
                quick_text = ""
                for i in range(min(2, len(doc))):
                    quick_text += doc[i].get_text()
                doc.close()
                quick_lower = quick_text.lower()
                # Banks where native PDF mode produces better results (complex two-column layouts)
                native_banks = ["banco itau", "itaú", "itau unibanco", "financeira itau cbd"]
                if any(ind in quick_lower for ind in native_banks):
                    use_native = True
                    print(
                        "[GoogleProvider] Auto-detected Itaú layout — switching to native PDF mode"
                    )
            except Exception:
                pass

        print(
            f"[GoogleProvider] Using PDF {'native' if use_native else 'text'} mode, model={self.model}"
        )

        temp_file = None
        try:
            # Helper function para ler arquivo (definida ANTES do uso)
            def _read_file_sync(path):
                with open(path, "rb") as f:
                    return f.read()

            # Salvar PDF em arquivo temporario (em thread separada)
            def _write_temp():
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(pdf_content)
                    return f.name

            temp_file = await asyncio.to_thread(_write_temp)

            # Try native mode: send PDF bytes directly to Gemini
            if use_native and not password:
                print("[GoogleProvider] Native mode: sending PDF bytes directly to Gemini...")

                # Extract text only for bank detection (lightweight)
                from ..pdf_text_extractor import PDFTextExtractor

                pdf_bytes = await asyncio.to_thread(_read_file_sync, temp_file)
                try:
                    ocr_text = PDFTextExtractor.extract_text_with_layout(pdf_bytes, password)
                    bank_name = self._detect_bank(ocr_text)
                except Exception:
                    bank_name = None

                composed_prompt = self._compose_prompt_with_bank(bank_name)

                native_prompt = f"""{composed_prompt}

⚠️ IMPORTANTE: Retorne um OBJETO JSON com esta estrutura:
{{
  "document_type": "fatura_cartao",
  "card_info": {{ ... }},
  "items": [{{ ... }}]
}}

NÃO retorne apenas um array! Retorne um objeto completo.
Extraia TODAS as transações do documento PDF anexado."""

                contents = [
                    types.Part.from_bytes(data=pdf_content, mime_type="application/pdf"),
                    native_prompt,
                ]
                config = types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=self.response_schema,
                )
            else:
                if use_native and password:
                    print("[GoogleProvider] Password-protected PDF, falling back to text mode...")

                # PASSO 1: Usar PyMuPDF para extrair texto preservando layout de colunas
                print("[GoogleProvider] Step 1: Extract text with PyMuPDF (preserves columns)...")
                from ..pdf_text_extractor import PDFTextExtractor

                pdf_bytes = await asyncio.to_thread(_read_file_sync, temp_file)
                ocr_text = PDFTextExtractor.extract_text_with_layout(pdf_bytes, password)
                print(f"[GoogleProvider] Text extracted with layout: {len(ocr_text)} chars")

                # Log das primeiras linhas para debug
                lines_preview = "\n".join(ocr_text.split("\n")[:30])
                print(f"[GoogleProvider] Text preview:\n{lines_preview}\n...")

                # PASSO 2: Detectar banco e compor prompt
                bank_name = self._detect_bank(ocr_text)
                composed_prompt = self._compose_prompt_with_bank(bank_name)

                # PASSO 3: Fazer extração estruturada usando TEXTO (não imagem)
                print("[GoogleProvider] Step 2: Structured extraction from TEXT (not image)...")

                # Criar prompt final com o texto do documento
                final_prompt = f"""{composed_prompt}

## TEXTO EXTRAÍDO DO DOCUMENTO

Abaixo está o texto completo extraído do PDF com layout preservado.
As colunas estão representadas lado a lado na mesma linha.

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

NÃO retorne apenas um array! Retorne um objeto completo."""

                # Preparar conteudo e config (apenas texto, sem imagem)
                contents = [final_prompt]
                config = types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=self.response_schema,
                )

            last_error = None
            for attempt in range(self.max_retries):
                try:
                    print(
                        f"[GoogleProvider] Calling Gemini API (attempt {attempt + 1}/{self.max_retries})..."
                    )
                    # Executa em thread separada para nao bloquear o event loop
                    response = await asyncio.to_thread(
                        self._generate_content_sync, client, self.model, contents, config
                    )

                    response_text = response.text if response else ""
                    print(f"[GoogleProvider] Response length: {len(response_text)} chars")
                    return self._parse_response(response_text)

                except Exception as e:
                    last_error = e
                    print(
                        f"[GoogleProvider] API error (attempt {attempt + 1}): {type(e).__name__}: {e}"
                    )
                    if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2**attempt)
                        print(f"[GoogleProvider] Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise

            return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

        finally:
            if temp_file and os.path.exists(temp_file):
                await asyncio.to_thread(os.unlink, temp_file)

    async def extract_multi_page(self, images: list[tuple[bytes, str]]) -> dict:
        """Extrai dados de multiplas paginas usando SDK oficial (non-blocking)"""
        try:
            from google.genai import types
        except ImportError:
            print("[GoogleProvider] google.genai not available, using httpx fallback")
            return await self._call_multi_page_httpx(images)

        client = self._get_client()
        print(f"[GoogleProvider] Using Google SDK, model={self.model}")

        parts = [
            self.prompt
            + "\n\n ATENCAO: Este documento tem MULTIPLAS PAGINAS. Extraia TODAS as transacoes de TODAS as paginas!"
        ]

        for i, (img_content, img_mime) in enumerate(images):
            parts.append(types.Part.from_bytes(data=img_content, mime_type=img_mime))
            parts.append(f"[Pagina {i + 1} de {len(images)}]")

        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=32000,  # Increased for large receipts with many items
            response_mime_type="application/json",
            response_schema=self.response_schema,
        )

        last_error = None
        for attempt in range(self.max_retries):
            try:
                print(
                    f"[GoogleProvider] Calling Gemini API (attempt {attempt + 1}/{self.max_retries})..."
                )
                # Executa em thread separada para nao bloquear o event loop
                response = await asyncio.to_thread(
                    self._generate_content_sync, client, self.model, parts, config
                )

                response_text = response.text if response else ""
                print(f"[GoogleProvider] Response length: {len(response_text)} chars")
                return self._parse_response(response_text)

            except Exception as e:
                last_error = e
                print(
                    f"[GoogleProvider] API error (attempt {attempt + 1}): {type(e).__name__}: {e}"
                )
                if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    print(f"[GoogleProvider] Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

    async def _call_httpx(self, image_content: bytes, mime_type: str) -> dict:
        """Fallback: Chama Google Gemini API via httpx"""
        import httpx

        api_key = settings.google_api_key
        if not api_key:
            return {"items": [], "error": "GOOGLE_API_KEY nao configurada"}

        image_base64 = base64.b64encode(image_content).decode("utf-8")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                        headers={
                            "x-goog-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "contents": [
                                {
                                    "parts": [
                                        {"text": self.prompt},
                                        {
                                            "inline_data": {
                                                "mime_type": mime_type,
                                                "data": image_base64,
                                            }
                                        },
                                    ]
                                }
                            ],
                            "generationConfig": {
                                "temperature": 0.1,
                                "maxOutputTokens": 16000,
                            },
                        },
                    )

                    if response.status_code != 200:
                        error_msg = f"Google API error: {response.status_code}"
                        if response.status_code in [503, 429]:
                            raise Exception(error_msg)
                        return {"items": [], "error": error_msg}

                    result = response.json()
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
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

    async def _call_multi_page_httpx(self, images: list[tuple[bytes, str]]) -> dict:
        """Fallback: Chama Google Gemini API com multiplas paginas via httpx"""
        import httpx

        api_key = settings.google_api_key
        if not api_key:
            return {"items": [], "error": "GOOGLE_API_KEY nao configurada"}

        parts = [
            {
                "text": self.prompt
                + "\n\n ATENCAO: Este documento tem MULTIPLAS PAGINAS. Extraia TODAS as transacoes de TODAS as paginas!"
            }
        ]

        for i, (img_content, img_mime) in enumerate(images):
            image_base64 = base64.b64encode(img_content).decode("utf-8")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": img_mime,
                        "data": image_base64,
                    }
                }
            )
            parts.append({"text": f"[Pagina {i + 1} de {len(images)}]"})

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                        headers={
                            "x-goog-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "contents": [{"parts": parts}],
                            "generationConfig": {
                                "temperature": 0.1,
                                "maxOutputTokens": 32000,
                            },
                        },
                    )

                    if response.status_code != 200:
                        error_msg = f"Google API error: {response.status_code}"
                        if response.status_code in [503, 429]:
                            raise Exception(error_msg)
                        return {"items": [], "error": error_msg}

                    result = response.json()
                    if not result.get("candidates"):
                        return {"items": [], "error": "Google API retornou resposta vazia"}

                    content = result["candidates"][0]["content"]["parts"][0]["text"]
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

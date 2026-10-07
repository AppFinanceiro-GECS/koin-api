"""Mistral provider para extracao de documentos via OCR especializado"""

import asyncio
import io
import logging
from pathlib import Path

from app.core.config import settings

from ..document_classifier import DocumentClassifier, DocumentType
from .base import BaseProvider

logger = logging.getLogger(__name__)


DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
# Tamanho maximo para imagens antes de comprimir (2MB)
MAX_IMAGE_SIZE_MB = 2.0

# Singleton Mistral client para reutilização
_mistral_client = None
_mistral_client_lock = asyncio.Lock()


async def get_mistral_client():
    """
    Retorna um cliente Mistral singleton.
    Evita criar novo cliente a cada requisicao.
    """
    global _mistral_client

    if _mistral_client is not None:
        return _mistral_client

    async with _mistral_client_lock:
        # Double-check pattern
        if _mistral_client is not None:
            return _mistral_client

        api_key = settings.mistral_api_key
        if not api_key:
            raise ValueError("MISTRAL_API_KEY nao configurada")

        try:
            try:
                from mistralai import Mistral
            except ImportError:
                from mistralai.client import Mistral

            # Cliente singleton - a biblioteca Mistral gerencia conexoes internamente
            _mistral_client = Mistral(api_key=api_key)
            logger.info("[MistralProvider] Cliente Mistral singleton inicializado")
            return _mistral_client

        except ImportError:
            raise ImportError("mistralai nao instalado. Execute: pip install mistralai")


def compress_image_sync(image_bytes: bytes, max_size_mb: float = MAX_IMAGE_SIZE_MB) -> bytes:
    """
    Comprime imagem se exceder tamanho maximo.
    Mantém qualidade aceitavel para OCR.
    Otimizado para memoria: reutiliza buffer e fecha imagens explicitamente.
    """
    import gc

    max_size = int(max_size_mb * 1024 * 1024)
    if len(image_bytes) <= max_size:
        return image_bytes

    img = None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))

        # Converter para RGB se necessario
        if img.mode in ("RGBA", "P"):
            old_img = img
            img = img.convert("RGB")
            old_img.close()

        # Usar um unico buffer reutilizado
        buffer = io.BytesIO()

        # Tentar comprimir reduzindo qualidade
        for quality in range(85, 25, -10):
            buffer.seek(0)
            buffer.truncate()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            if buffer.tell() <= max_size:
                result = buffer.getvalue()
                return result

        # Se ainda muito grande, redimensionar
        width, height = img.size
        for scale in [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]:
            new_size = (int(width * scale), int(height * scale))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            buffer.seek(0)
            buffer.truncate()
            resized.save(buffer, format="JPEG", quality=70, optimize=True)
            resized.close()  # Fechar imagem redimensionada imediatamente
            if buffer.tell() <= max_size:
                result = buffer.getvalue()
                return result

        # Retornar ultima tentativa mesmo se ainda grande
        result = buffer.getvalue()
        return result

    except Exception as e:
        logger.error("compress_image_sync_failed error_type=%s", type(e).__name__)
        return image_bytes

    finally:
        # Fechar imagem e forcar GC
        if img is not None:
            try:
                img.close()
            except Exception:
                pass
        gc.collect()


class MistralProvider(BaseProvider):
    """Provider Mistral para extracao via OCR especializado + LLM"""

    def __init__(
        self,
        model: str | None = None,
        prompt: str = "",
        parse_response_fn=None,
        use_classifier: bool = True,
    ):
        super().__init__(model or settings.mistral_llm_model)
        self.max_retries = DEFAULT_MAX_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.prompt = prompt
        self._parse_response = parse_response_fn or (lambda x: {"items": [], "error": "No parser"})
        self.classifier = DocumentClassifier() if use_classifier else None
        logger.info("[MistralProvider] Initialized with classifier=%s", use_classifier)

    def _upload_sync(self, client, pdf_content: bytes, filename: str):
        """Upload sincrono do PDF para Mistral"""
        return client.files.upload(
            file={
                "file_name": filename,
                "content": pdf_content,
            },
            purpose="ocr",
        )

    def _ocr_sync(self, client, file_id: str):
        """OCR sincrono do PDF"""
        return client.ocr.process(
            model=settings.mistral_ocr_model,
            document={
                "type": "file",
                "file_id": file_id,
            },
            include_image_base64=False,
        )

    def _chat_sync(self, client, full_prompt: str):
        """Chat sincrono com LLM"""
        return client.chat.complete(
            model=settings.mistral_llm_model,
            messages=[{"role": "user", "content": full_prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=32000,  # Aumentado para cupons grandes com muitos itens
        )

    async def _get_prompt(self, ocr_text: str = "") -> tuple[str, str]:
        """Carrega o prompt apropriado baseado no tipo de documento detectado.

        Returns:
            tuple[str, str]: (prompt_text, document_type)
        """
        prompts_dir = Path(__file__).parent.parent.parent / "prompts"

        # Usar novo classificador se disponivel
        if self.classifier:
            logger.info("[MistralProvider] Usando DocumentClassifier...")
            doc_type_enum = await self.classifier.classify(ocr_text, max_chars=3000)

            if doc_type_enum == DocumentType.CUPOM_FISCAL:
                doc_type = "cupom_fiscal"
                prompt_path = prompts_dir / "cupom_fiscal_focused.md"
                logger.info(
                    "[MistralProvider] Tipo detectado: CUPOM_FISCAL -> usando prompt focado"
                )
            elif doc_type_enum == DocumentType.FATURA_CARTAO:
                doc_type = "fatura_cartao"
                prompt_path = prompts_dir / "fatura_cartao_focused.md"
                logger.info(
                    "[MistralProvider] Tipo detectado: FATURA_CARTAO -> usando prompt focado"
                )
            else:
                # Fallback: usar metodo antigo
                logger.info("[MistralProvider] Tipo UNKNOWN, usando deteccao antiga...")
                doc_type = self._detect_document_type(ocr_text)
                if doc_type == "cupom_fiscal":
                    prompt_path = prompts_dir / "cupom_fiscal_focused.md"
                else:
                    prompt_path = prompts_dir / "fatura_cartao_focused.md"
        else:
            # Fallback: usar metodo antigo
            doc_type = self._detect_document_type(ocr_text)
            logger.info("[MistralProvider] Tipo detectado (metodo antigo): %s", doc_type)

            if doc_type == "cupom_fiscal":
                prompt_path = prompts_dir / "cupom_fiscal_focused.md"
            else:
                prompt_path = prompts_dir / "fatura_cartao_focused.md"

        # Carregar prompt base
        if prompt_path.exists():
            prompt_text = prompt_path.read_text(encoding="utf-8")
        else:
            # Fallback: prompt generico
            prompt_text = self.prompt

        # Se for fatura de cartão, tentar carregar prompt específico do banco
        if doc_type == "fatura_cartao":
            bank_name = self._detect_bank(ocr_text)
            if bank_name:
                bank_prompt_path = prompts_dir / "banks" / f"{bank_name}.md"
                if bank_prompt_path.exists():
                    bank_prompt = bank_prompt_path.read_text(encoding="utf-8")
                    # Compor: prompt geral + prompt específico do banco
                    prompt_text = f"{prompt_text}\n\n{bank_prompt}"

        return prompt_text, doc_type

    def _detect_bank(self, ocr_text: str) -> str | None:
        """Detecta o banco emissor da fatura a partir do texto OCR.

        Returns:
            Nome do banco em lowercase (ex: "itau", "nubank", "bradesco")
            ou None se não detectar
        """
        text_lower = ocr_text.lower()

        # Mapeamento de indicadores para nomes de bancos
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

    def _detect_document_type(self, ocr_text: str) -> str:
        """Detecta se é cupom fiscal ou fatura de cartão."""
        text_lower = ocr_text.lower()

        # Indicadores de cupom fiscal / NFC-e
        cupom_indicators = [
            "cupom fiscal",
            "nfc-e",
            "nota fiscal",
            "danfe",
            "cnpj",
            "item codigo descricao",
            "qtde un vl unit",
            "valor total r$",
            "forma de pagamento",
            "troco",
            "chave de acesso",
            "protocolo de autorizacao",
            "qr code",
            "consumidor final",
        ]

        # Indicadores de fatura de cartão
        fatura_indicators = [
            "fatura",
            "vencimento",
            "limite de credito",
            "limite disponivel",
            "pagamento minimo",
            "encargos",
            "parcelamento",
            "total a pagar",
            "cartao final",
            "nubank",
            "itau",
            "bradesco",
            "santander",
            "banco",
        ]

        cupom_score = sum(1 for indicator in cupom_indicators if indicator in text_lower)
        fatura_score = sum(1 for indicator in fatura_indicators if indicator in text_lower)

        return "cupom_fiscal" if cupom_score > fatura_score else "fatura_cartao"

    async def extract_from_image(
        self, image_content: bytes, mime_type: str, password: str | None = None
    ) -> dict:
        """Converte imagem para PDF e processa via OCR

        Args:
            image_content: Image file content as bytes
            mime_type: MIME type of the image
            password: Optional password (not used for images, only for consistency)
        """
        # Converter imagem para PDF
        pdf_content = await self._image_to_pdf(image_content, mime_type)
        return await self.extract_from_pdf(pdf_content, "image.pdf", password)

    async def extract_multi_page(self, images: list[tuple[bytes, str]]) -> dict:
        """Converte multiplas imagens para PDF e processa via OCR"""
        logger.info("[MistralProvider] Convertendo %s imagens para PDF...", len(images))
        pdf_content = await self._images_to_pdf(images)
        return await self.extract_from_pdf(pdf_content, "multi_page.pdf")

    async def _image_to_pdf(self, image_content: bytes, mime_type: str) -> bytes:
        """Converte uma imagem para PDF"""
        return await self._images_to_pdf([(image_content, mime_type)])

    async def _images_to_pdf(self, images: list[tuple[bytes, str]]) -> bytes:
        """
        Converte multiplas imagens para um unico PDF, dividindo páginas muito longas.
        Otimizado para memoria: fecha imagens explicitamente e roda gc.collect() periodicamente.
        """
        import gc

        from PIL import Image

        def _split_long_image(
            img: Image.Image, max_ratio: float = 3.0
        ) -> tuple[list[Image.Image], bool]:
            """
            Divide uma imagem muito longa em seções verticais menores.
            Retorna (sections, was_split) para saber se deve fechar a imagem original.
            """
            width, height = img.size
            ratio = height / width

            if ratio <= max_ratio:
                return [img], False

            # Calcular quantas seções precisamos
            num_sections = int(ratio / max_ratio) + 1
            section_height = height // num_sections

            # Overlap de 10% da altura da seção para não cortar texto
            overlap = max(100, int(section_height * 0.10))
            sections = []

            for i in range(num_sections):
                top = max(0, i * section_height - (overlap if i > 0 else 0))
                bottom = min(
                    height, (i + 1) * section_height + (overlap if i < num_sections - 1 else 0)
                )

                section = img.crop((0, top, width, bottom))
                sections.append(section)

            return sections, True

        def _convert():
            pdf_images = []

            for idx, (img_content, _) in enumerate(images):
                img = None
                try:
                    # Comprimir imagem antes de converter para PDF
                    img_content = compress_image_sync(img_content)

                    img = Image.open(io.BytesIO(img_content))
                    if img.mode in ("RGBA", "P"):
                        old_img = img
                        img = img.convert("RGB")
                        old_img.close()

                    # Dividir se for muito longa
                    sections, was_split = _split_long_image(img)
                    pdf_images.extend(sections)

                    # Se foi dividido, fechar a imagem original (as sections sao novas)
                    if was_split:
                        img.close()
                        img = None  # Evitar fechar novamente no finally

                finally:
                    # Liberar referencia dos bytes da imagem
                    del img_content

                # GC a cada 3 imagens para evitar pico de memoria
                if (idx + 1) % 3 == 0:
                    gc.collect()

            # Criar PDF
            output = io.BytesIO()
            try:
                if len(pdf_images) == 1:
                    pdf_images[0].save(output, format="PDF")
                else:
                    pdf_images[0].save(
                        output, format="PDF", save_all=True, append_images=pdf_images[1:]
                    )
                result = output.getvalue()
            finally:
                # Fechar todas as imagens do PDF
                for img in pdf_images:
                    try:
                        img.close()
                    except Exception:
                        pass
                pdf_images.clear()
                gc.collect()

            return result

        return await asyncio.to_thread(_convert)

    async def _split_long_pdf(
        self, pdf_content: bytes, max_ratio: float = 3.0, password: str | None = None
    ) -> bytes:
        """
        Detecta e divide PDFs com páginas muito longas.
        Otimizado para memoria: processa pagina por pagina e libera recursos imediatamente.

        Args:
            pdf_content: PDF file content as bytes
            max_ratio: Maximum height/width ratio before splitting
            password: Optional password for protected PDFs

        Raises:
            PasswordRequiredException: If PDF requires password and none provided
        """
        import gc
        import io

        from PIL import Image

        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.info("[MistralProvider] PyMuPDF não instalado, não é possível dividir PDF longo")
            return pdf_content

        # Import PasswordRequiredException
        from ..pdf_converter import PasswordRequiredException

        def _process():
            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # Check if password is required
            if doc.needs_pass:
                if password is None:
                    doc.close()
                    raise PasswordRequiredException("PDF protegido por senha")

                # Try to authenticate with provided password
                auth_result = doc.authenticate(password)
                if auth_result == 0:
                    doc.close()
                    raise ValueError("Senha incorreta")

            # Continue with normal processing after successful authentication

            # If PDF was password-protected, we need to return the decrypted version
            # even if it doesn't need splitting
            pdf_was_encrypted = doc.needs_pass or password is not None

            # Primeira passagem: apenas verificar se precisa dividir (sem armazenar imagens)
            needs_split = False
            for page_num in range(len(doc)):
                page = doc[page_num]
                rect = page.rect
                ratio = rect.height / rect.width
                if ratio > max_ratio:
                    needs_split = True
                    break

            if not needs_split and not pdf_was_encrypted:
                # No split needed and no decryption - return original
                doc.close()
                return pdf_content

            if not needs_split and pdf_was_encrypted:
                # PDF was password-protected
                # Mistral OCR has issues with decrypted PDFs (corrupts content)
                # Return None to force fallback to image-based processing
                logger.info(
                    "[MistralProvider] PDF was encrypted - forcing image-based processing..."
                )
                doc.close()
                return None  # Force fallback to convert_pdf_to_images

            logger.info(
                "[MistralProvider] PDF com página longa detectado, processando %s página(s)...",
                len(doc),
            )

            # Segunda passagem: processar pagina por pagina
            final_images = []

            try:
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    mat = fitz.Matrix(2, 2)  # 2x zoom para melhor qualidade
                    pix = page.get_pixmap(matrix=mat)

                    # Converter para PIL Image
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    # Liberar pixmap imediatamente
                    del pix

                    width, height = img.size
                    ratio = height / width

                    if ratio <= max_ratio:
                        final_images.append(img)
                    else:
                        # Dividir a imagem
                        num_sections = int(ratio / max_ratio) + 1
                        section_height = height // num_sections
                        overlap = max(100, int(section_height * 0.10))

                        for i in range(num_sections):
                            top = max(0, i * section_height - (overlap if i > 0 else 0))
                            bottom = min(
                                height,
                                (i + 1) * section_height + (overlap if i < num_sections - 1 else 0),
                            )
                            section = img.crop((0, top, width, bottom))
                            final_images.append(section)

                        # Fechar imagem original apos dividir (as sections sao novas)
                        img.close()
                        logger.info(
                            "[MistralProvider] Página %s dividida em %s seções",
                            page_num + 1,
                            num_sections,
                        )

                    # GC periodico
                    if (page_num + 1) % 3 == 0:
                        gc.collect()

                doc.close()

                # Reconverter para PDF
                output = io.BytesIO()
                if len(final_images) == 1:
                    final_images[0].save(output, format="PDF")
                else:
                    final_images[0].save(
                        output, format="PDF", save_all=True, append_images=final_images[1:]
                    )

                result = output.getvalue()
                logger.info("[MistralProvider] PDF recriado com %s páginas", len(final_images))
                return result

            finally:
                # Cleanup: fechar todas as imagens
                for img in final_images:
                    try:
                        img.close()
                    except Exception:
                        pass
                final_images.clear()
                gc.collect()

        return await asyncio.to_thread(_process)

    def _build_annotation_prompt(self, bank_prompt: str = "") -> str:
        """Build a concise annotation prompt for document_annotation."""
        base = (
            "Extraia TODAS as transações desta fatura de cartão de crédito brasileiro.\n\n"
            "REGRAS CRÍTICAS:\n"
            "- Extraia APENAS lançamentos ATUAIS (seção 'Lançamentos' ou 'compras e saques' e 'produtos e serviços')\n"
            "- NÃO extraia a seção 'Compras parceladas - próximas faturas'\n"
            "- NÃO extraia 'PAG BOLETO BANCARIO' ou pagamentos de fatura anterior\n"
            "- Se há DUAS COLUNAS de lançamentos, extraia AMBAS\n"
            "- Itens com mesma descrição mas valores diferentes são compras DISTINTAS\n"
            "- A soma dos amounts deve ser igual ao total_amount da fatura\n"
            "- Datas: use formato YYYY-MM-DD. O formato DD/MM na fatura indica dia/mês REAL da compra\n"
            "- Para determinar o ano: se mês da transação > mês da fatura, use ano anterior\n"
            "- Valores negativos para créditos/estornos\n"
            "- BRADESCO/AMEX: '-' APÓS o valor indica crédito/pagamento (NÃO extrair pagamentos, usar amount negativo para créditos)\n"
            "- BRADESCO/AMEX: Ignore a coluna 'Cidade' da tabela (não é descrição)\n"
        )
        if bank_prompt:
            base += f"\n{bank_prompt}"
        return base

    def _ocr_with_annotation_sync(
        self, client, file_id: str, annotation_format, annotation_prompt: str
    ):
        """OCR com document_annotation - extrai texto + dados estruturados em uma chamada."""
        return client.ocr.process(
            model=settings.mistral_ocr_model,
            document={
                "type": "file",
                "file_id": file_id,
            },
            include_image_base64=True,
            document_annotation_format=annotation_format,
            document_annotation_prompt=annotation_prompt,
        )

    async def _try_annotation_extraction(
        self, client, uploaded_file, bank_prompt: str = ""
    ) -> tuple[dict | None, str]:
        """
        Try extracting with document_annotation (single API call).
        Returns (result, ocr_text) or (None, ocr_text) if annotation failed.
        """
        from ..schemas import AnnotationExtracao

        try:
            from mistralai.extra import response_format_from_pydantic_model

            annotation_format = response_format_from_pydantic_model(AnnotationExtracao)
        except (ImportError, Exception) as e:
            logger.error("_try_annotation_extraction_failed error_type=%s", type(e).__name__)
            return None, ""

        annotation_prompt = self._build_annotation_prompt(bank_prompt)

        logger.info("[MistralProvider] Trying document_annotation (single-call extraction)...")

        try:
            ocr_response = await asyncio.to_thread(
                self._ocr_with_annotation_sync,
                client,
                uploaded_file.id,
                annotation_format,
                annotation_prompt,
            )
        except Exception as e:
            logger.error("_try_annotation_extraction_failed error_type=%s", type(e).__name__)
            return None, ""

        # Extract OCR text (always available)
        ocr_text = ""
        if hasattr(ocr_response, "pages"):
            for page in ocr_response.pages:
                if hasattr(page, "markdown"):
                    ocr_text += page.markdown + "\n\n"

        # Check for annotation result
        annotation_json = getattr(ocr_response, "document_annotation", None)
        # Handle UNSET sentinel from Mistral SDK
        if annotation_json is None or (
            hasattr(annotation_json, "__class__") and "UNSET" in str(type(annotation_json))
        ):
            logger.info("[MistralProvider] document_annotation returned no structured data")
            return None, ocr_text

        if not isinstance(annotation_json, str) or not annotation_json.strip():
            logger.info(
                "[MistralProvider] document_annotation empty or invalid type: %s",
                type(annotation_json),
            )
            return None, ocr_text

        logger.info("[MistralProvider] document_annotation returned %s chars", len(annotation_json))

        # Parse through existing parser (handles normalization, validation, etc.)
        result = self._parse_response(annotation_json)

        if not result.get("items"):
            logger.info("[MistralProvider] document_annotation parsed but no items found")
            return None, ocr_text

        # Validate sum
        card_info = result.get("card_info") or {}
        total_amount = card_info.get("total_amount")
        items_sum = sum(
            item.get("amount", 0) for item in result["items"] if item.get("amount", 0) > 0
        )

        if total_amount and abs(total_amount - items_sum) <= 100:
            result["_ocr_text"] = ocr_text
            result["_ocr_text_preview"] = (
                ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text
            )
            return result, ocr_text
        else:
            # Return annotation result as candidate (might still be better than LLM)
            result["_ocr_text"] = ocr_text
            result["_ocr_text_preview"] = (
                ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text
            )
            result["_annotation_candidate"] = True
            return result, ocr_text

    async def extract_from_pdf(
        self, pdf_content: bytes, filename: str = "document.pdf", password: str | None = None
    ) -> dict:
        """
        Extrai dados de um PDF usando Mistral OCR.

        Estratégia:
        1. Tenta document_annotation (OCR + extração estruturada em 1 chamada)
        2. Se annotation falhar ou soma não bater, cai no fluxo OCR text + LLM chat
        3. Compara resultados e retorna o melhor

        Args:
            pdf_content: PDF file content as bytes
            filename: Original filename
            password: Optional password for protected PDFs

        Raises:
            PasswordRequiredException: If PDF requires password and none provided
        """
        # Pré-processar PDF para dividir páginas muito longas
        pdf_content = await self._split_long_pdf(pdf_content, password=password)

        # If password-protected PDF, fallback to image processing
        if pdf_content is None:
            logger.info("[MistralProvider] Returning None to force image-based processing")
            return None

        try:
            client = await get_mistral_client()
        except (ValueError, ImportError) as e:
            return {"items": [], "card_info": None, "document_type": None, "error": str(e)}

        try:
            # Step 1: Upload PDF (single upload, reused for annotation and fallback)
            logger.info(
                "[MistralProvider] Passo 1: Fazendo upload do PDF (%s bytes)...", len(pdf_content)
            )
            uploaded_file = await asyncio.to_thread(
                self._upload_sync, client, pdf_content, filename
            )

            # Step 2: Try document_annotation (OCR + structured extraction in 1 call)
            # Uses generic prompt since we don't know the bank yet
            annotation_result, ocr_text = await self._try_annotation_extraction(
                client, uploaded_file, bank_prompt=""
            )

            # If annotation returned no OCR text, do a separate OCR call (reuse file_id)
            if not ocr_text.strip():
                logger.info(
                    "[MistralProvider] Annotation didn't return OCR text, doing separate OCR (reusing file_id)..."
                )
                ocr_response = await asyncio.to_thread(self._ocr_sync, client, uploaded_file.id)
                if hasattr(ocr_response, "pages"):
                    for page in ocr_response.pages:
                        if hasattr(page, "markdown"):
                            ocr_text += page.markdown + "\n\n"

            logger.info("[MistralProvider] OCR extraiu %s caracteres", len(ocr_text))

            if not ocr_text.strip():
                return {
                    "items": [],
                    "card_info": None,
                    "document_type": None,
                    "error": "OCR nao extraiu texto do PDF",
                }

            # If annotation succeeded with good sum match, return it directly
            if annotation_result and not annotation_result.get("_annotation_candidate"):
                logger.info("[MistralProvider] Using document_annotation result (perfect match)")
                return annotation_result

            # Step 3: Fallback to OCR text + LLM chat
            logger.info(
                "[MistralProvider] Passo 3: Estruturando com LLM %s...", settings.mistral_llm_model
            )

            prompt, detected_doc_type = await self._get_prompt(ocr_text)
            full_prompt = f"{prompt}\n\n## Texto extraido do PDF pelo OCR:\n\n{ocr_text}"

            logger.info("[MistralProvider] Tipo final detectado: %s", detected_doc_type)

            last_error = None
            for attempt in range(self.max_retries):
                try:
                    chat_response = await asyncio.to_thread(self._chat_sync, client, full_prompt)

                    response_text = chat_response.choices[0].message.content
                    logger.info("[MistralProvider] LLM retornou %s caracteres", len(response_text))

                    llm_result = self._parse_response(response_text)

                    if llm_result.get("items"):
                        llm_result["_ocr_text"] = ocr_text
                        llm_result["_ocr_text_preview"] = (
                            ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text
                        )

                        # Retry with feedback if sum mismatch
                        llm_result = await self._retry_if_sum_mismatch(
                            llm_result, client, full_prompt, ocr_text
                        )

                    # Compare annotation vs LLM result — pick the one with better sum match
                    if annotation_result and annotation_result.get("_annotation_candidate"):
                        best = self._pick_best_result(annotation_result, llm_result)
                        best.pop("_annotation_candidate", None)
                        return best

                    return llm_result

                except Exception as e:
                    last_error = e
                    if self._is_retryable_error(e) and attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2**attempt)
                        logger.info(
                            "[MistralProvider] Erro retryable, aguardando %ss...", wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # LLM failed — use annotation as fallback if available
                        if annotation_result and annotation_result.get("items"):
                            logger.info(
                                "[MistralProvider] LLM failed (%s), using annotation fallback (%s items)",
                                type(e).__name__,
                                len(annotation_result["items"]),
                            )
                            annotation_result.pop("_annotation_candidate", None)
                            return annotation_result
                        raise

            # If LLM loop exhausted but annotation had a candidate, use it
            if annotation_result and annotation_result.get("items"):
                logger.info(
                    "[MistralProvider] LLM exhausted retries, using annotation fallback (%s items)",
                    len(annotation_result["items"]),
                )
                annotation_result.pop("_annotation_candidate", None)
                return annotation_result

            return {"items": [], "error": f"Falha apos {self.max_retries} tentativas: {last_error}"}

        except Exception as e:
            logger.error("extract_from_pdf_failed error_type=%s", type(e).__name__)

            return {
                "items": [],
                "card_info": None,
                "document_type": None,
                "error": f"Mistral error: {str(e)}",
            }

    def _pick_best_result(self, result_a: dict, result_b: dict) -> dict:
        """Pick the result with the best sum match to total_amount."""

        def _score(result):
            if not result or not result.get("items"):
                return float("inf")
            card_info = result.get("card_info") or {}
            total = card_info.get("total_amount")
            if not total:
                return float("inf")
            items_sum = sum(i.get("amount", 0) for i in result["items"] if i.get("amount", 0) > 0)
            return abs(total - items_sum)

        score_a = _score(result_a)
        score_b = _score(result_b)

        if score_a <= score_b:
            return result_a
        else:
            return result_b

    def _find_missing_amounts_in_ocr(self, ocr_text: str, extracted_items: list) -> list[str]:
        """Scan OCR text for amounts that were not extracted, to provide targeted retry feedback."""
        import re

        # Extract all monetary amounts from OCR text (format: 123,45 or 1.234,56)
        amount_pattern = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")
        ocr_amounts = []
        for match in amount_pattern.finditer(ocr_text):
            raw = match.group(1)
            # Convert Brazilian format to float
            value = float(raw.replace(".", "").replace(",", "."))
            if 5 <= value <= 10000:  # Reasonable transaction range
                ocr_amounts.append(value)

        # Get all extracted amounts
        extracted_amounts = [item.get("amount", 0) for item in extracted_items]

        # Find amounts in OCR that don't match any extracted amount (with tolerance)
        missing = []
        used_extracted = list(extracted_amounts)
        for ocr_amt in ocr_amounts:
            matched = False
            for i, ext_amt in enumerate(used_extracted):
                if abs(ocr_amt - ext_amt) < 0.02:
                    used_extracted.pop(i)
                    matched = True
                    break
            if not matched:
                missing.append(ocr_amt)

        # Deduplicate and sort by value descending
        seen = set()
        unique_missing = []
        for amt in missing:
            rounded = round(amt, 2)
            if rounded not in seen:
                seen.add(rounded)
                unique_missing.append(rounded)
        unique_missing.sort(reverse=True)

        # Find context (nearby text) for each missing amount
        results = []
        for amt in unique_missing[:10]:  # Limit to top 10
            # Search for this amount in OCR text to get context
            amt_str_comma = f"{amt:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            # Also try without thousand separator
            amt_str_simple = f"{amt:.2f}".replace(".", ",")

            context = ""
            for pattern_str in [amt_str_comma, amt_str_simple]:
                idx = ocr_text.find(pattern_str)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(ocr_text), idx + len(pattern_str) + 5)
                    context = ocr_text[start:end].replace("\n", " ").strip()
                    break

            if context:
                results.append(f'  - R$ {amt:.2f} → contexto OCR: "{context}"')
            else:
                results.append(f"  - R$ {amt:.2f}")

        return results

    async def _retry_if_sum_mismatch(
        self, result: dict, client, full_prompt: str, ocr_text: str
    ) -> dict:
        """Retry LLM extraction once if sum of items diverges from total_amount by > R$50."""
        card_info = result.get("card_info") or {}
        total_amount = card_info.get("total_amount")
        if not total_amount or not result.get("items"):
            return result

        items_sum = sum(
            item.get("amount", 0) for item in result["items"] if item.get("amount", 0) > 0
        )
        diff = total_amount - items_sum

        if abs(diff) <= 50:
            return result

        logger.info("[MistralProvider] Retrying with feedback...")

        # Identify specific missing amounts from OCR text
        missing_amounts_info = self._find_missing_amounts_in_ocr(ocr_text, result["items"])
        missing_details = (
            "\n".join(missing_amounts_info)
            if missing_amounts_info
            else "  (não foi possível identificar os valores específicos)"
        )

        feedback = (
            f"\n\n## ⚠️ ERRO NA EXTRAÇÃO ANTERIOR - CORRIJA AGORA\n\n"
            f"A soma dos itens extraídos foi R$ {items_sum:.2f}, mas o total_amount da fatura é R$ {total_amount:.2f}.\n"
            f"**Faltam R$ {diff:.2f} em transações!**\n\n"
            f"**VALORES ENCONTRADOS NO OCR MAS NÃO EXTRAÍDOS:**\n"
            f"{missing_details}\n\n"
            f"**POSSÍVEIS CAUSAS:**\n"
            f"- A página 2 tem DUAS COLUNAS lado a lado. Você extraiu AMBAS?\n"
            f"- NÃO confunda a seção 'Compras parceladas - próximas faturas' (que NÃO deve ser extraída) com os lançamentos ATUAIS\n"
            f"- Os lançamentos ATUAIS aparecem ANTES da linha 'Total dos lançamentos atuais'\n"
            f"- As 'próximas faturas' aparecem DEPOIS, com parcelas de número MAIOR (ex: 09/12 em vez de 08/12)\n\n"
            f"**REFAÇA A EXTRAÇÃO COMPLETA. Extraia TODOS os itens de TODAS as colunas de lançamentos atuais.**\n"
        )

        retry_prompt = full_prompt + feedback
        retry_result = None

        try:
            retry_response = await asyncio.to_thread(self._chat_sync, client, retry_prompt)
            retry_text = retry_response.choices[0].message.content
            logger.info("[MistralProvider] Retry LLM retornou %s caracteres", len(retry_text))

            retry_result = self._parse_response(retry_text)

            if retry_result.get("items"):
                retry_sum = sum(
                    item.get("amount", 0)
                    for item in retry_result["items"]
                    if item.get("amount", 0) > 0
                )
                retry_diff = abs(retry_sum - total_amount)
                original_diff = abs(diff)

                if retry_diff < original_diff:
                    retry_result["_ocr_text"] = ocr_text
                    retry_result["_ocr_text_preview"] = (
                        ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text
                    )
                    return retry_result
        except Exception as e:
            logger.error("_retry_if_sum_mismatch_failed error_type=%s", type(e).__name__)

        # If retry didn't help enough, try OCR-based recovery
        best_result = result
        best_sum = items_sum
        if retry_result and retry_result.get("items"):
            retry_sum_val = sum(
                item.get("amount", 0) for item in retry_result["items"] if item.get("amount", 0) > 0
            )
            if abs(retry_sum_val - total_amount) < abs(best_sum - total_amount):
                best_result = retry_result
                best_sum = retry_sum_val

        remaining_diff = total_amount - best_sum
        if abs(remaining_diff) > 50:
            recovered = self._recover_missing_from_ocr(ocr_text, best_result)
            if recovered:
                best_result = recovered

        return best_result

    def _recover_missing_from_ocr(self, ocr_text: str, result: dict) -> dict | None:
        """
        Parse OCR text directly to find transaction lines missing from extraction.
        Only recovers items from the 'Lançamentos' section (before 'Total dos lançamentos'
        and before 'Compras parceladas - próximas faturas').
        Returns updated result or None if no recovery was possible.
        """
        import re

        if not ocr_text or not result.get("items"):
            return None

        card_info = result.get("card_info") or {}
        total_amount = card_info.get("total_amount")
        if not total_amount:
            return None

        # Find boundaries of the current transactions section
        ocr_lower = ocr_text.lower()

        lancamentos_start = 0
        for marker in [
            "lançamentos: compras e saques",
            "lancamentos: compras e saques",
            "lançamentos:compras e saques",
        ]:
            idx = ocr_lower.find(marker)
            if idx >= 0:
                lancamentos_start = idx
                break

        # Find end: "Total dos lançamentos atuais" or "Compras parceladas - próximas faturas"
        lancamentos_end = len(ocr_text)
        for end_marker in [
            "total dos lançamentos atuais",
            "total dos lancamentos atuais",
            "compras parceladas - próximas faturas",
            "compras parceladas - proximas faturas",
            "compras parceladas-próximas faturas",
            "compras parceladas - próximas",
            "compras parceladas-próximas",
        ]:
            idx = ocr_lower.find(end_marker)
            if idx > lancamentos_start:
                lancamentos_end = min(lancamentos_end, idx)

        relevant_text = ocr_text[lancamentos_start:lancamentos_end]
        if not relevant_text:
            logger.info("[MistralProvider] OCR recovery: no relevant section found in OCR text")
            return None

        logger.info(
            "[MistralProvider] OCR recovery: scanning %s chars of relevant OCR text",
            len(relevant_text),
        )

        # Parse transaction lines: DD/MM description amount
        # Itaú format: "09/07 MOTOCHEFE BRASILIA08/12 574,13"
        tx_pattern = re.compile(
            r"(\d{2}/\d{2})\s+"  # date DD/MM
            r"(.+?)\s+"  # description (non-greedy)
            r"(\d{1,3}(?:\.\d{3})*,\d{2})"  # amount
        )

        ocr_transactions = []
        for match in tx_pattern.finditer(relevant_text):
            date_str = match.group(1)
            desc = match.group(2).strip()
            amount_str = match.group(3)
            amount = float(amount_str.replace(".", "").replace(",", "."))

            if amount < 1:
                continue

            ocr_transactions.append(
                {
                    "date_str": date_str,
                    "description": desc,
                    "amount": amount,
                }
            )

        if not ocr_transactions:
            logger.info("[MistralProvider] OCR recovery: no transaction lines found in OCR text")
            return None

        logger.info(
            "[MistralProvider] OCR recovery: found %s transactions in OCR text",
            len(ocr_transactions),
        )

        # Find which OCR transactions are missing from extracted items
        extracted_amounts = []
        for item in result["items"]:
            extracted_amounts.append(
                {
                    "amount": item.get("amount", 0),
                    "used": False,
                }
            )

        missing_txs = []
        for ocr_tx in ocr_transactions:
            matched = False
            for ext in extracted_amounts:
                if not ext["used"] and abs(ext["amount"] - ocr_tx["amount"]) < 0.02:
                    ext["used"] = True
                    matched = True
                    break
            if not matched:
                missing_txs.append(ocr_tx)

        if not missing_txs:
            logger.info("[MistralProvider] OCR recovery: all OCR transactions already matched")
            return None

        # Build new items from missing transactions
        invoice_month = card_info.get("invoice_month")
        invoice_year = card_info.get("invoice_year")

        new_items = []
        for tx in missing_txs:
            day, month = tx["date_str"].split("/")
            day, month = int(day), int(month)

            if invoice_year and invoice_month:
                year = invoice_year if month <= invoice_month else invoice_year - 1
            else:
                year = 2026

            date_str = f"{year}-{month:02d}-{day:02d}"

            # Parse installment info from description (e.g., "MOTOCHEFE BRASILIA08/12")
            installment_match = re.search(r"(\d{2})/(\d{2})\s*$", tx["description"])
            is_installment = False
            installment_current = None
            installment_total = None

            if installment_match:
                installment_current = int(installment_match.group(1))
                installment_total = int(installment_match.group(2))
                is_installment = True

            new_item = {
                "description": tx["description"],
                "amount": tx["amount"],
                "date": date_str,
                "category": "diversos",
                "confidence": 0.75,
                "transaction_type": "compra",
                "is_installment": is_installment,
                "installment_current": installment_current,
                "installment_total": installment_total,
            }
            new_items.append(new_item)

        if not new_items:
            return None

        # Verify adding items improves sum match
        current_sum = sum(
            item.get("amount", 0) for item in result["items"] if item.get("amount", 0) > 0
        )
        new_sum = current_sum + sum(item["amount"] for item in new_items if item["amount"] > 0)

        if abs(new_sum - total_amount) >= abs(current_sum - total_amount):
            return None

        updated_result = dict(result)
        updated_result["items"] = list(result["items"]) + new_items
        updated_result["_ocr_text"] = ocr_text
        updated_result["_ocr_text_preview"] = (
            ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text
        )
        return updated_result

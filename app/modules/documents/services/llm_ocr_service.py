"""Servico de extracao de dados usando LLM com visao (multi-provider)

Este modulo foi refatorado para seguir Clean Code:
- Providers separados em providers/
- Validacao em extraction_validator.py
- Parser em response_parser.py
- Conversao PDF em pdf_converter.py
- Classificador de documentos em document_classifier.py
"""

from pathlib import Path

from app.core.config import settings

from .document_classifier import DocumentClassifier
from .extraction_validator import ExtractionValidator
from .pdf_converter import convert_pdf_to_images
from .prompts import EXTRACTION_PROMPT
from .providers import AnthropicProvider, GoogleProvider, MistralProvider, OpenAIProvider
from .response_parser import ResponseParser
from .schemas import FaturaExtracao


class LLMOCRService:
    """Extrai dados de imagens usando LLM com visao (suporta multiplos providers)"""

    def __init__(
        self, provider: str | None = None, model: str | None = None, use_classifier: bool = True
    ):
        self.provider_name = provider or settings.vision_provider
        self.model = model or settings.vision_model or "gemini-2.0-flash"
        self.parser = ResponseParser()
        self.validator = ExtractionValidator()
        self.classifier = DocumentClassifier() if use_classifier else None
        self._provider = None
        self._prompts_cache = {}  # Cache de prompts carregados
        print(
            f"[LLM_OCR] Initialized: provider={self.provider_name}, model={self.model}, classifier={use_classifier}"
        )

    def _load_prompt(self, filename: str) -> str:
        """Carrega prompt de arquivo (com cache)"""
        if filename in self._prompts_cache:
            return self._prompts_cache[filename]

        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_path = prompts_dir / filename

        if prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8")
            self._prompts_cache[filename] = prompt
            return prompt

        # Fallback para prompt generico
        print(f"[LLM_OCR] AVISO: Prompt {filename} nao encontrado, usando EXTRACTION_PROMPT")
        return EXTRACTION_PROMPT

    def _get_provider(self, prompt: str | None = None):
        """Retorna o provider configurado (lazy initialization)

        Args:
            prompt: Prompt customizado (se None, usa EXTRACTION_PROMPT)
        """
        # Nota: Para simplificar, estamos criando provider com prompt padrao
        # O prompt especifico sera passado diretamente nas chamadas quando necessario
        if self._provider is None:
            parse_fn = self.parser.parse
            default_prompt = prompt or EXTRACTION_PROMPT

            if self.provider_name == "google":
                self._provider = GoogleProvider(
                    model=self.model,
                    prompt=default_prompt,
                    response_schema=FaturaExtracao,
                    parse_response_fn=parse_fn,
                )
            elif self.provider_name == "mistral":
                self._provider = MistralProvider(
                    model=self.model, prompt=default_prompt, parse_response_fn=parse_fn
                )
            elif self.provider_name == "openai":
                self._provider = OpenAIProvider(
                    model=self.model, prompt=default_prompt, parse_response_fn=parse_fn
                )
            elif self.provider_name == "anthropic":
                self._provider = AnthropicProvider(
                    model=self.model, prompt=default_prompt, parse_response_fn=parse_fn
                )
            else:
                raise ValueError(f"Provider nao suportado: {self.provider_name}")

        return self._provider

    async def extract_from_image(
        self,
        image_content: bytes,
        mime_type: str = "image/png",
        filename: str = "document",
        password: str | None = None,
    ) -> dict:
        """Extrai dados do documento usando o provider configurado

        Args:
            image_content: Conteudo binario do arquivo
            mime_type: Tipo MIME (image/png, application/pdf, etc.)
            filename: Nome do arquivo original
            password: Optional password for protected PDFs

        Returns:
            Dict com items, card_info, document_type ou error
        """
        print(
            f"[LLM_OCR] extract_from_image: provider={self.provider_name}, mime_type={mime_type}, size={len(image_content)}"
        )

        try:
            is_pdf = mime_type == "application/pdf" or mime_type.endswith("/pdf")

            provider = self._get_provider()

            # 1. Tentar processar diretamente (PDF ou imagem)
            if is_pdf:
                print(f"[LLM_OCR] Processing PDF via {self.provider_name}")
                try:
                    result = await provider.extract_from_pdf(image_content, filename, password)
                except Exception as primary_err:
                    # Primary provider failed — try fallback before giving up
                    print(
                        f"[LLM_OCR] Primary provider ({self.provider_name}) failed: {type(primary_err).__name__}: {primary_err}"
                    )
                    fallback_provider = self._get_fallback_provider()
                    if fallback_provider:
                        print("[LLM_OCR] Trying fallback provider...")
                        result = await fallback_provider.extract_from_pdf(
                            image_content, filename, password
                        )
                    else:
                        raise

                # Se provider retornou None, precisa converter para imagens
                if result is None:
                    print("[LLM_OCR] Provider nao suporta PDF direto, convertendo para imagens...")
                    result = await self._process_pdf_as_images(image_content, password)
            else:
                result = await provider.extract_from_image(image_content, mime_type)

            # 2. Se nao conseguiu extrair, retorna erro
            if not result or result.get("error"):
                return result or {"items": [], "error": "Extracao falhou"}

            # 2.5. Quality-based retry: 0 items from multi-page PDF -> try fallback provider
            items_before_retry = result.get("items", [])
            if is_pdf and not items_before_retry:
                pdf_page_count = self._get_pdf_page_count(image_content)
                if pdf_page_count > 1:
                    fallback_provider = self._get_fallback_provider()
                    if fallback_provider:
                        print(
                            f"[LLM_OCR] 0 items extracted from {pdf_page_count}-page PDF, retrying with fallback provider"
                        )
                        try:
                            retry_result = await fallback_provider.extract_from_pdf(
                                image_content, filename, password
                            )
                            if (
                                retry_result
                                and not retry_result.get("error")
                                and retry_result.get("items")
                            ):
                                print(
                                    f"[LLM_OCR] Fallback succeeded: {len(retry_result['items'])} items extracted"
                                )
                                result = retry_result
                            else:
                                print("[LLM_OCR] Fallback also returned 0 items or error")
                        except Exception as retry_err:
                            print(
                                f"[LLM_OCR] Fallback retry failed: {type(retry_err).__name__}: {retry_err}"
                            )

            # 3. Aplicar validacoes e limpezas
            items = result.get("items", [])
            card_info = result.get("card_info")
            document_type = result.get("document_type")
            # Total pode vir no root ou dentro de card_info (cupom_fiscal)
            total_amount = result.get("total_amount") or (
                card_info.get("total_amount") if card_info else None
            )

            # DEBUG: Log para verificar total_amount
            print(f"[LLM_OCR] DEBUG: document_type={document_type}, total_amount={total_amount}")
            print(f"[LLM_OCR] DEBUG: result keys={list(result.keys())}")
            if "total_amount" in result:
                print(f"[LLM_OCR] DEBUG: result['total_amount']={result.get('total_amount')}")

            # Extrair OCR text (disponível quando Mistral provider é usado)
            ocr_text = result.pop("_ocr_text", None)

            if items:
                items = self.validator.validate_and_clean(
                    items, card_info, document_type, total_amount, ocr_text=ocr_text
                )
                result["items"] = items

                # Validar resultado final
                validation = self.validator.validate_extraction(items, card_info)
                if not validation["is_valid"]:
                    print(
                        f"[LLM_OCR] AVISO: Validacao falhou - diff={validation['difference']:.2f}"
                    )

                # Divergence warning: sum of amounts vs card_info total
                if card_info and card_info.get("total_amount") is not None:
                    items_sum = sum(item.get("amount", 0) for item in items)
                    card_total = card_info["total_amount"]
                    divergence = abs(items_sum - card_total)
                    if divergence > 100:
                        print(
                            f"[LLM_OCR] WARNING: items sum R$ {items_sum:.2f} diverges from "
                            f"card_info.total R$ {card_total:.2f} by R$ {divergence:.2f} (>R$100)"
                        )

            return result

        except Exception as e:
            print(f"[LLM_OCR] Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return {"items": [], "error": str(e)}

    def _create_provider(self, provider_name: str):
        """Create a specific provider instance (used for fallback)."""
        parse_fn = self.parser.parse
        default_prompt = EXTRACTION_PROMPT

        if provider_name == "google":
            return GoogleProvider(
                model="gemini-2.0-flash",
                prompt=default_prompt,
                response_schema=FaturaExtracao,
                parse_response_fn=parse_fn,
            )
        elif provider_name == "mistral":
            return MistralProvider(
                model=None,
                prompt=default_prompt,
                parse_response_fn=parse_fn,
            )
        else:
            raise ValueError(f"Provider not supported for routing: {provider_name}")

    def _get_fallback_provider(self):
        """Returns a fallback provider for retry, or None if unavailable.

        Strategy:
        - google -> try mistral (if api key exists)
        - mistral -> try google (if api key exists)
        - otherwise -> None
        """
        parse_fn = self.parser.parse

        if self.provider_name == "google" and settings.mistral_api_key:
            print("[LLM_OCR] Fallback provider: mistral")
            return MistralProvider(
                model=None,
                prompt=self._provider.prompt if self._provider else EXTRACTION_PROMPT,
                parse_response_fn=parse_fn,
            )
        elif self.provider_name == "mistral" and settings.google_api_key:
            print("[LLM_OCR] Fallback provider: google")
            return GoogleProvider(
                model="gemini-2.0-flash",
                prompt=self._provider.prompt if self._provider else EXTRACTION_PROMPT,
                response_schema=FaturaExtracao,
                parse_response_fn=parse_fn,
            )

        print("[LLM_OCR] No fallback provider available")
        return None

    def _get_pdf_page_count(self, pdf_bytes: bytes) -> int:
        """Returns the number of pages in a PDF, or 0 on error."""
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    async def _process_pdf_as_images(self, pdf_content: bytes, password: str | None = None) -> dict:
        """Fallback: converte PDF para imagens e processa

        Args:
            pdf_content: PDF file content as bytes
            password: Optional password for protected PDFs

        Raises:
            PasswordRequiredException: If PDF requires password
        """
        images, pdf_error = await convert_pdf_to_images(pdf_content, password)

        if pdf_error:
            return {"items": [], "error": pdf_error}
        if not images:
            return {"items": [], "error": "PDF nao gerou imagens para processar"}

        provider = self._get_provider()

        # Se temos multiplas paginas, enviar todas juntas para dar contexto completo ao LLM
        # Isso evita processar página por página e perder contexto
        if len(images) > 1 and self.provider_name in ("google", "mistral"):
            print(f"[LLM_OCR] Processing {len(images)} pages together for full context")
            return await provider.extract_multi_page(images)

        # Processar paginas separadamente
        all_items = []
        all_page_results = []  # Store all page results for post-processing
        document_type = None
        errors = []

        for page_num, (img_content, img_mime) in enumerate(images, 1):
            page_result = await provider.extract_from_image(img_content, img_mime)
            all_page_results.append((page_num, page_result))

            if page_result.get("error"):
                errors.append(f"Pagina {page_num}: {page_result['error']}")
            if page_result.get("items"):
                all_items.extend(page_result["items"])
            if page_result.get("document_type") and not document_type:
                document_type = page_result["document_type"]

        if not all_items and errors:
            return {"items": [], "error": "; ".join(errors)}

        # Post-processing: Filter items for main card only (if multiple cards detected)
        # First, find the real card number (ignoring known placeholders)
        CARD_PLACEHOLDERS = {"0000", "****", "XXXX", "9999", "1234", "xxxx", "1809", "0960"}

        # Count occurrences of each card number to find the main card
        from collections import Counter

        card_counts = Counter()
        for page_num, page_result in all_page_results:
            page_card = page_result.get("card_info", {}).get("card_last_digits")
            if page_card and page_card not in CARD_PLACEHOLDERS:
                card_counts[page_card] += 1

        all_cards = set(card_counts.keys())

        # Determine the main card: use the one that appears most frequently
        main_card = None
        card_info = None  # Will be set to the main card's card_info

        if all_cards:
            # Use the card that appears most times (not just first occurrence)
            main_card = card_counts.most_common(1)[0][0]
            print(
                f"[LLM_OCR] Found real card numbers: {dict(card_counts)}, using most frequent: {main_card}"
            )

            # Get card_info from a page with the main card (prefer page with most complete info)
            for page_num, page_result in all_page_results:
                page_card = page_result.get("card_info", {}).get("card_last_digits")
                if page_card == main_card:
                    page_card_info = page_result.get("card_info")
                    # Prefer card_info with more fields filled
                    if page_card_info:
                        if card_info is None:
                            card_info = page_card_info
                        elif page_card_info.get("credit_limit") and not card_info.get(
                            "credit_limit"
                        ):
                            card_info = page_card_info

        # Fallback: if no card_info found yet, use first available
        if card_info is None:
            for page_num, page_result in all_page_results:
                if page_result.get("card_info"):
                    card_info = page_result["card_info"]
                    break

        if main_card:
            # First pass: Remove pages with placeholder card numbers or example data
            # These often contain summary/example data, not real transactions
            valid_page_results = []
            skipped_pages = []
            for page_num, page_result in all_page_results:
                page_card = page_result.get("card_info", {}).get("card_last_digits")
                page_items = page_result.get("items", [])

                # Skip pages with placeholder if we have a real card
                if page_card in CARD_PLACEHOLDERS and main_card not in CARD_PLACEHOLDERS:
                    skipped_pages.append((page_num, f"placeholder card {page_card}"))
                    continue

                # Additional heuristic: Detect pages with example/simulation data
                # Example data often has:
                # 1. Round numbers (100.00, 200.00, 300.00)
                # 2. No installments
                # 3. Generic company names (LTDA, S.A., EIRELI, MEI)
                if page_items and len(page_items) >= 3:
                    round_values = sum(1 for item in page_items if item.get("amount", 0) % 100 == 0)
                    no_installments = sum(
                        1 for item in page_items if not item.get("is_installment")
                    )
                    generic_names = sum(
                        1
                        for item in page_items
                        if any(
                            suffix in item.get("description", "").upper()
                            for suffix in [" LTDA", " S.A.", " EIRELI", " MEI"]
                        )
                    )

                    # If > 50% are round values, no installments, and generic names → likely example data
                    is_likely_example = (
                        round_values >= len(page_items) * 0.5
                        and no_installments >= len(page_items) * 0.7
                        and generic_names >= len(page_items) * 0.5
                    )

                    if is_likely_example:
                        skipped_pages.append((page_num, "example data detected"))
                        print(
                            f"[LLM_OCR] Page {page_num} looks like example data (round:{round_values}, no_inst:{no_installments}, generic:{generic_names})"
                        )
                        continue

                valid_page_results.append((page_num, page_result))

            if skipped_pages:
                print(f"[LLM_OCR] Skipped placeholder pages: {skipped_pages}")

            # Second pass: If multiple real cards detected, filter by main card
            if len(all_cards) > 1:
                print(
                    f"[LLM_OCR] Multiple real cards detected: {all_cards}, keeping only: {main_card}"
                )
                # Keep only items from pages with the main card
                filtered_items = []
                for page_num, page_result in valid_page_results:
                    page_card = page_result.get("card_info", {}).get("card_last_digits")
                    page_items = page_result.get("items", [])
                    if (
                        page_card == main_card or not page_card
                    ):  # Include if matches main card or no card info
                        filtered_items.extend(page_items)
                    else:
                        print(
                            f"[LLM_OCR] Skipping {len(page_items)} items from page {page_num} (card {page_card})"
                        )

                print(f"[LLM_OCR] Filtered {len(all_items)} -> {len(filtered_items)} items")
                all_items = filtered_items
            elif len(valid_page_results) < len(all_page_results):
                # Some pages were skipped due to placeholder, rebuild items list
                all_items = []
                for page_num, page_result in valid_page_results:
                    all_items.extend(page_result.get("items", []))
                print(
                    f"[LLM_OCR] Filtered pages: kept {len(valid_page_results)}/{len(all_page_results)} pages, {len(all_items)} items"
                )

        # Post-processing: Remove duplicate installments (same item, different installment number)
        # Keep only the installment with the LOWEST installment_current (earliest)
        if all_items:
            seen_installments = {}  # key: (description, total), value: item with lowest current
            non_installment_items = []

            for item in all_items:
                if (
                    item.get("is_installment")
                    and item.get("installment_current")
                    and item.get("installment_total")
                ):
                    # Normalize description for comparison
                    desc = item.get("description", "").upper().strip()
                    # Remove common suffixes that might vary
                    for suffix in [" LTDA", " S.A.", " EIRELI", " MEI", " ME"]:
                        if desc.endswith(suffix):
                            desc = desc[: -len(suffix)].strip()

                    # Normalize spaces (some OCRs add/remove spaces inconsistently)
                    import re

                    desc = re.sub(r"\s+", "", desc)  # Remove all spaces for comparison

                    total = item.get("installment_total")
                    amount = item.get("amount", 0)
                    # Include amount in key — same merchant can have different purchases
                    # with different amounts (e.g., EC *PICHAU R$166.64 and R$85.61)
                    key = (desc, total, amount)

                    if key not in seen_installments:
                        seen_installments[key] = item
                    else:
                        # Keep the one with lowest installment_current
                        existing = seen_installments[key]
                        if item.get("installment_current") < existing.get("installment_current"):
                            print(
                                f"[LLM_OCR] Replacing duplicate installment: {desc} {existing.get('installment_current')}/{total} R${amount} -> {item.get('installment_current')}/{total} R${amount}"
                            )
                            seen_installments[key] = item
                        else:
                            print(
                                f"[LLM_OCR] Skipping duplicate installment: {desc} {item.get('installment_current')}/{total} R${amount} (keeping {existing.get('installment_current')}/{total})"
                            )
                else:
                    non_installment_items.append(item)

            # Rebuild items list
            filtered_items = list(seen_installments.values()) + non_installment_items
            if len(filtered_items) < len(all_items):
                print(
                    f"[LLM_OCR] Removed {len(all_items) - len(filtered_items)} duplicate installments: {len(all_items)} -> {len(filtered_items)} items"
                )
                all_items = filtered_items

        # Validação de soma para faturas de cartão
        validation_warning = None
        if document_type == "fatura_cartao" and card_info and card_info.get("total_amount"):
            total_amount = card_info.get("total_amount")
            items_sum = sum(item.get("amount", 0) for item in all_items)
            difference = abs(total_amount - items_sum)

            print(
                f"[LLM_OCR] Sum validation: total={total_amount:.2f}, sum={items_sum:.2f}, diff={difference:.2f}"
            )

            if difference > 50:
                validation_warning = {
                    "type": "sum_mismatch",
                    "expected": total_amount,
                    "actual": items_sum,
                    "difference": difference,
                    "message": f"ALERTA: Soma dos itens (R$ {items_sum:.2f}) difere do total da fatura (R$ {total_amount:.2f}) em R$ {difference:.2f}. Possível causa: LLM ignorou alguma coluna/seção de transações.",
                }
                print(f"[LLM_OCR] ⚠️ {validation_warning['message']}")

        result = {
            "items": all_items,
            "document_type": document_type,
            "card_info": card_info,
        }

        if validation_warning:
            result["validation_warning"] = validation_warning

        return result

    async def extract_from_multiple_images(
        self,
        images: list[tuple[bytes, str]],  # (content, mime_type)
    ) -> dict:
        """Extrai dados de multiplas imagens (cupons grandes)

        Args:
            images: Lista de tuples (content, mime_type)

        Returns:
            Dict com items, card_info, document_type ou error
        """
        print(
            f"[LLM_OCR] extract_from_multiple_images: provider={self.provider_name}, num_images={len(images)}"
        )

        try:
            provider = self._get_provider()

            # Usar extract_multi_page (Google e Mistral suportam)
            if self.provider_name in ("google", "mistral"):
                result = await provider.extract_multi_page(images)
            else:
                # Fallback: processar separadamente e consolidar
                all_items = []
                document_type = None
                card_info = None
                errors = []

                for page_num, (img_content, img_mime) in enumerate(images, 1):
                    page_result = await provider.extract_from_image(img_content, img_mime)

                    if page_result.get("error"):
                        errors.append(f"Imagem {page_num}: {page_result['error']}")
                    if page_result.get("items"):
                        all_items.extend(page_result["items"])
                    if page_result.get("document_type") and not document_type:
                        document_type = page_result["document_type"]
                    if page_result.get("card_info") and not card_info:
                        card_info = page_result["card_info"]

                if not all_items and errors:
                    return {"items": [], "error": "; ".join(errors)}

                result = {
                    "items": all_items,
                    "document_type": document_type,
                    "card_info": card_info,
                }

            # Aplicar validacoes e limpezas
            if result and not result.get("error"):
                items = result.get("items", [])
                card_info = result.get("card_info")
                document_type = result.get("document_type")
                # Total pode vir no root ou dentro de card_info (cupom_fiscal)
                total_amount = result.get("total_amount") or (
                    card_info.get("total_amount") if card_info else None
                )

                if items:
                    items = self.validator.validate_and_clean(
                        items, card_info, document_type, total_amount
                    )
                    result["items"] = items

                    validation = self.validator.validate_extraction(items, card_info)
                    if not validation["is_valid"]:
                        print(
                            f"[LLM_OCR] AVISO: Validacao falhou - diff={validation['difference']:.2f}"
                        )

            return result

        except Exception as e:
            print(f"[LLM_OCR] Error in extract_from_multiple_images: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return {"items": [], "error": str(e)}
